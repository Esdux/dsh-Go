#!/usr/bin/env python3
"""Re-applies this fork's local changes after syncing upstream.

Upstream ships the stock behaviour; three things here are ours and a merge would
otherwise overwrite them:

  * the island chip says 「吃白饭」 for the generic working states and never falls
    back to the chat title;
  * a keep-alive foreground service keeps a remote (SSH/relay) link alive while the
    app is in the background;
  * the composer can paste a picture straight off the system clipboard.

Idempotent: run it after every merge; a clean tree means nothing to do. Files a merge
deleted or replaced are restored from the first parent (the branch we merged into).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITS = 0


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def write(path: Path, text: str) -> None:
    global EDITS
    # Bytes on purpose: text mode would turn LF into CRLF on a Windows host.
    path.write_bytes(text.encode('utf-8'))
    EDITS += 1


def restore(path: str) -> None:
    """A merge dropped one of our files: take it back from the previous commit."""
    target = ROOT / path
    if target.exists():
        return
    for rev in ('HEAD^1', 'HEAD~1'):
        done = subprocess.run(['git', 'checkout', rev, '--', path], cwd=ROOT,
                              capture_output=True, text=True)
        if done.returncode == 0 and target.exists():
            print(f'restored {path} from {rev}')
            return
    print(f'! {path} is missing and could not be restored', file=sys.stderr)


def insert_after(path: str, anchor: str, payload: str, marker: str) -> None:
    """Put payload right after the line holding anchor, unless marker is already present."""
    target = ROOT / path
    if not target.is_file():
        print(f'! {path} is missing', file=sys.stderr)
        return
    text = read(target)
    if marker in text:
        return
    at = text.find(anchor)
    if at < 0:
        print(f'! {path}: anchor not found: {anchor[:60]!r}', file=sys.stderr)
        return
    end = text.find('\n', at)
    write(target, text[:end + 1] + payload + text[end + 1:])


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    if not target.is_file():
        print(f'! {path} is missing', file=sys.stderr)
        return
    text = read(target)
    if new in text:
        return
    if old not in text:
        print(f'! {path}: pattern not found: {old[:60]!r}', file=sys.stderr)
        return
    write(target, text.replace(old, new, 1))


def patch_arb(path: str, values: dict[str, str]) -> None:
    target = ROOT / path
    if not target.is_file():
        print(f'! {path} is missing', file=sys.stderr)
        return
    text = read(target)
    changed = False
    for key, value in values.items():
        pattern = re.compile(r'("' + re.escape(key) + r'"\s*:\s*)"[^"]*"')
        text, hits = pattern.subn(lambda m, v=value: m.group(1) + '"' + v + '"', text)
        if hits:
            changed = True
    if changed:
        write(target, text)


# --- island chip ---------------------------------------------------------------

def replace_chip_words() -> None:
    """The accessor keeps the indent it has; only the expression changes."""
    target = ROOT / 'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/notify/LiveContent.kt'
    if not target.is_file():
        print('! LiveContent.kt is missing', file=sys.stderr)
        return
    text = read(target)
    match = re.search(r'(?m)^([ \t]*)val chipWords: String\? get\(\) = (.+)$', text)
    if match is None:
        print('! LiveContent.kt: chipWords accessor not found', file=sys.stderr)
        return
    if match.group(2).strip() == 'chip?.takeIf { it.isNotBlank() }':
        return
    write(target, text[:match.start(2)] + 'chip?.takeIf { it.isNotBlank() }' + text[match.end(2):])


def patch_chip() -> None:
    zh = {
        'liveChipThinking': '吃白饭',
        'liveChipWorking': '吃白饭',
        'liveChipJuggling': '吃白饭',
        'liveChipSweeping': '吃白饭',
    }
    en = {key: 'Eating plain rice' for key in zh}
    patch_arb('app/lib/l10n/parts/live_zh.arb', zh)
    patch_arb('app/lib/l10n/parts/live_en.arb', en)
    replace_chip_words()


# --- remote link keep-alive ----------------------------------------------------

KEEPALIVE_SERVICE = 'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/remote/LinkKeepAliveService.kt'
KEEPALIVE_DART = 'app/lib/remote/link_keepalive.dart'
KEEPALIVE_STRINGS = [
    'app/android/app/src/main/res/values/link_keepalive_strings.xml',
    'app/android/app/src/main/res/values-zh/link_keepalive_strings.xml',
]


def patch_keepalive() -> None:
    for path in [KEEPALIVE_SERVICE, KEEPALIVE_DART, *KEEPALIVE_STRINGS]:
        restore(path)
    insert_after(
        'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/runtime/RuntimePlugin.kt',
        'import android.provider.Settings',
        'import io.github.ccch1mneyyy.dsh_app.remote.LinkKeepAliveService\n',
        'remote.LinkKeepAliveService',
    )
    insert_after(
        'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/runtime/RuntimePlugin.kt',
        '"getStatus" -> result.success(controller.status())',
        '''            "startLinkKeepAlive" -> {
                try {
                    LinkKeepAliveService.start(appContext)
                    result.success(true)
                } catch (_: Exception) {
                    result.success(false)
                }
            }
            "stopLinkKeepAlive" -> {
                LinkKeepAliveService.stop(appContext)
                result.success(true)
            }
''',
        'startLinkKeepAlive',
    )
    insert_after(
        'app/android/app/src/main/AndroidManifest.xml',
        '<!-- Keeps the floating pet\'s process up when only remote hosts are used',
        '''        <service
            android:name=".remote.LinkKeepAliveService"
            android:exported="false"
            android:foregroundServiceType="specialUse">
            <property
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="Keeps the user's remote agent session connected in the background" />
        </service>

        <!-- Keeps a remote host link alive in the background (remote/LinkKeepAliveService.kt). -->
''',
        'remote.LinkKeepAliveService',
    )
    insert_after(
        'app/lib/runtime/runtime_bridge.dart',
        "  Future<void> clearFailure() => _methods.invokeMethod<void>('clearFailure');",
        '''
  /// Keeps the process up while a remote host is connected and the app is in the
  /// background (Android only). False when the system refused the start.
  Future<bool> startLinkKeepAlive() async =>
      await _methods.invokeMethod<bool>('startLinkKeepAlive') ?? false;

  Future<void> stopLinkKeepAlive() => _methods.invokeMethod<void>('stopLinkKeepAlive');
''',
        'startLinkKeepAlive',
    )
    insert_after(
        'app/lib/ui/notify/background_net_host.dart',
        "import '../../runtime/background_net.dart';",
        "import '../../remote/link_keepalive.dart';\n",
        'link_keepalive.dart',
    )
    insert_after(
        'app/lib/ui/notify/background_net_host.dart',
        '    _lifecycle = AppLifecycleListener(',
        '    ref.read(linkKeepAliveProvider);\n',
        'linkKeepAliveProvider',
    )


# --- paste a picture from the clipboard ----------------------------------------

CLIPBOARD_IMAGES = 'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/clipboard/ClipboardImages.kt'
CLIPBOARD_DART = 'app/lib/clipboard/clipboard_image.dart'


def patch_clipboard() -> None:
    for path in [CLIPBOARD_IMAGES, CLIPBOARD_DART]:
        restore(path)
    insert_after(
        'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/runtime/RuntimePlugin.kt',
        'import io.github.ccch1mneyyy.dsh_app.remote.LinkKeepAliveService',
        'import io.github.ccch1mneyyy.dsh_app.clipboard.ClipboardImages\n',
        'clipboard.ClipboardImages',
    )
    insert_after(
        'app/android/app/src/main/kotlin/io/github/ccch1mneyyy/dsh_app/runtime/RuntimePlugin.kt',
        '"getStatus" -> result.success(controller.status())',
        '            // A copied picture lives behind a content:// URI; the text clipboard cannot see it.\n'
        '            "readClipboardImage" -> result.success(ClipboardImages.read(appContext))\n',
        'readClipboardImage',
    )
    insert_after(
        'app/lib/ui/chat/composer.dart',
        '    this.onContentInserted,',
        '    this.onPasteImage,\n',
        'this.onPasteImage',
    )
    insert_after(
        'app/lib/ui/chat/composer.dart',
        '  final TextEditingController controller;',
        '''
  /// Reads a picture off the system clipboard into the tray; null hides the
  /// paste-image entry in the field's long-press menu.
  final Future<void> Function()? onPasteImage;
''',
        'final Future<void> Function()? onPasteImage;',
    )
    replace_once(
        'app/lib/ui/chat/composer.dart',
        '                  readOnly: dictating || phase == VoicePhase.starting,',
        '''                  contextMenuBuilder: widget.onPasteImage == null
                      ? null
                      : (menuContext, state) => AdaptiveTextSelectionToolbar.buttonItems(
                          anchors: state.contextMenuAnchors,
                          buttonItems: [
                            ...state.contextMenuButtonItems,
                            ContextMenuButtonItem(
                              label: appL10n.chatPasteImage,
                              onPressed: () {
                                state.hideToolbar();
                                unawaited(widget.onPasteImage!());
                              },
                            ),
                          ],
                        ),
                  readOnly: dictating || phase == VoicePhase.starting,''',
    )
    insert_after(
        'app/lib/ui/chat/chat_screen.dart',
        "import '../../l10n/l10n.dart';",
        "import '../../clipboard/clipboard_image.dart';\n",
        'clipboard_image.dart',
    )
    insert_after(
        'app/lib/ui/chat/chat_screen.dart',
        'onContentInserted: connected ? _pasteContent : null,',
        '                                    onPasteImage: connected ? _pasteImageFromClipboard : null,\n',
        'onPasteImage:',
    )
    insert_after(
        'app/lib/ui/chat/chat_screen.dart',
        '  void _addDrafts(List<DraftAttachment> picked, {String? problem}) {',
        '''  /// A picture on the system clipboard: into the tray, not sent.
  Future<void> _pasteImageFromClipboard() async {
    final image = await ref.read(clipboardImageProvider).read();
    if (!mounted) return;
    if (image == null) {
      _toast(appL10n.chatPasteImageEmpty);
      return;
    }
    _addDrafts([
      DraftAttachment.sniff('\${appL10n.fileImageName}.\${image.extension}', image.bytes),
    ]);
  }

''',
        '_pasteImageFromClipboard',
    )
    patch_arb('app/lib/l10n/parts/chat_zh.arb', {'chatPasteImage': '粘贴图片', 'chatPasteImageEmpty': '剪贴板里没有图片'})
    patch_arb('app/lib/l10n/parts/chat_en.arb', {'chatPasteImage': 'Paste image', 'chatPasteImageEmpty': 'No image on the clipboard'})


def main() -> int:
    patch_chip()
    patch_keepalive()
    patch_clipboard()
    print(f'local patches: {EDITS} edit(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
