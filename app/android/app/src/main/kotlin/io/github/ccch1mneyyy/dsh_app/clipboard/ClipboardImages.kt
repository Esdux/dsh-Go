package io.github.ccch1mneyyy.dsh_app.clipboard

import android.content.ClipboardManager
import android.content.Context
import android.net.Uri

/**
 * The picture on the system clipboard, if any.
 *
 * Android keeps a copied image behind a content:// URI, not inline bytes, so the text-only
 * clipboard surface Flutter exposes cannot see it. Reading the URI is the only way a
 * screenshot or a copied picture reaches the composer. A text-only clip yields null and stays
 * with the ordinary paste path.
 */
object ClipboardImages {
    private const val MAX_BYTES = 32 * 1024 * 1024

    fun read(context: Context): Map<String, Any>? {
        val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return null
        val clip = manager.primaryClip ?: return null
        for (index in 0 until clip.itemCount) {
            val uri = clip.getItemAt(index).uri ?: continue
            val bytes = readAll(context, uri) ?: continue
            val declared = context.contentResolver.getType(uri)
            val mime = (declared ?: sniff(bytes))?.takeIf { it.startsWith("image/") } ?: continue
            return mapOf(
                "bytes" to bytes,
                "mime" to mime,
                "name" to "clipboard." + extensionFor(mime),
            )
        }
        return null
    }

    private fun readAll(context: Context, uri: Uri): ByteArray? = try {
        context.contentResolver.openInputStream(uri)?.use { input ->
            val out = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(64 * 1024)
            var total = 0
            var tooLarge = false
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                total += read
                if (total > MAX_BYTES) {
                    tooLarge = true
                    break
                }
                out.write(buffer, 0, read)
            }
            if (tooLarge) null else out.toByteArray().takeIf { it.isNotEmpty() }
        }
    } catch (_: Exception) {
        null
    }

    private fun sniff(bytes: ByteArray): String? {
        fun at(offset: Int, vararg sig: Int): Boolean {
            if (bytes.size < offset + sig.size) return false
            for (i in sig.indices) if (bytes[offset + i] != sig[i].toByte()) return false
            return true
        }
        return when {
            at(0, 0x89, 0x50, 0x4E, 0x47) -> "image/png"
            at(0, 0xFF, 0xD8, 0xFF) -> "image/jpeg"
            at(0, 0x47, 0x49, 0x46, 0x38) -> "image/gif"
            at(0, 0x52, 0x49, 0x46, 0x46) && at(8, 0x57, 0x45, 0x42, 0x50) -> "image/webp"
            at(0, 0x42, 0x4D) -> "image/bmp"
            else -> null
        }
    }

    private fun extensionFor(mime: String): String = when (mime) {
        "image/png" -> "png"
        "image/jpeg" -> "jpg"
        "image/gif" -> "gif"
        "image/webp" -> "webp"
        "image/bmp" -> "bmp"
        else -> "img"
    }
}
