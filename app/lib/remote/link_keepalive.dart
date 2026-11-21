/// Keeps the process up while a remote host — SSH or relay — is connected and the app is in
/// the background.
///
/// The local engine owns DshService. A phone that only talks to remote hosts has no foreground
/// service, so Android freezes the process as soon as the app leaves the screen: the SSH keepalive
/// and the relay's ping/pong stop, the host drops the link, and coming back starts over. This
/// starts the minimal LinkKeepAliveService for exactly that case and stops it again when the app
/// returns, the host turns local, or the link is no longer connected.
///
/// Best effort by design: if Android refuses the background start, the link behaves as before.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../runtime/runtime_bridge.dart';
import '../runtime/runtime_state.dart';
import '../state/connection_state.dart';
import '../state/hosts_state.dart';

/// Whether the keep-alive service should be running (diagnostics and tests).
final linkKeepAliveProvider = NotifierProvider<LinkKeepAlive, bool>(LinkKeepAlive.new);

class LinkKeepAlive extends Notifier<bool> {
  AppLifecycleListener? _lifecycle;
  bool _visible = true;
  bool _connected = false;
  bool _running = false;
  HostRef? _host;

  RuntimeBridge get _bridge => ref.read(runtimeBridgeProvider);

  @override
  bool build() {
    _lifecycle ??= AppLifecycleListener(
      onHide: () => _setVisible(false),
      onShow: () => _setVisible(true),
      onDetach: () => unawaited(_stop()),
    );
    ref.onDispose(() {
      _lifecycle?.dispose();
      _lifecycle = null;
      unawaited(_stop());
    });
    final host = ref.watch(activeHostProvider);
    if (_host != host) {
      _host = host;
      _connected = false;
      if (!host.isLocal) {
        // A fresh subscription emits the link's current status immediately.
        ref.listen(hostLinkStatusProvider(host), (_, next) {
          _connected = next.value?.isConnected ?? false;
          _sync();
        });
      }
    }
    // A host switch can happen outside any lifecycle event; settle after the build.
    Future<void>.microtask(_sync);
    return _running;
  }

  void _setVisible(bool visible) {
    if (_visible == visible) return;
    _visible = visible;
    _sync();
  }

  void _sync() {
    // The local engine's own DshService already holds the process; one foreground
    // service is enough.
    final engine = ref.read(localRuntimeProvider).status.phase == RuntimePhase.running;
    final want = !_visible && _connected && _host?.isLocal == false && !engine;
    if (want == _running) return;
    _running = want;
    state = want;
    if (want) {
      unawaited(
        _bridge.startLinkKeepAlive().then((started) {
          // Android may refuse; never claim the link is protected then.
          if (!started && _running) {
            _running = false;
            state = false;
          }
        }).catchError((Object _) {
          _running = false;
          state = false;
        }),
      );
    } else {
      unawaited(_stop());
    }
  }

  Future<void> _stop() async {
    if (!_running) return;
    _running = false;
    try {
      await _bridge.stopLinkKeepAlive();
    } catch (_) {
      // The service may already be gone; nothing to recover.
    }
  }
}
