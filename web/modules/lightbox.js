// ── Lightbox for sponsor QR code images ─────────────────────────────
// Click a QR code -> fullscreen preview -> download button

let currentSrc = '';
let currentName = 'qrcode';

export function initLightbox() {
  const overlay = document.getElementById('lightboxOverlay');
  const lbImg = document.getElementById('lightboxImage');
  const closeBtn = document.getElementById('lightboxClose');
  const dlBtn = document.getElementById('lightboxDownload');

  if (!overlay || !lbImg) return;

  // Close helpers
  function close() {
    overlay.hidden = true;
    currentSrc = '';
  }

  if (closeBtn) closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close(); // tap dark area closes
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !overlay.hidden) close();
  });

  // Download helper
  if (dlBtn) {
    dlBtn.addEventListener('click', () => {
      downloadImage(currentSrc, currentName);
    });
  }

  // Wire every sponsor-card <img> as a trigger
  document.querySelectorAll('.support-card img').forEach((img) => {
    img.addEventListener('click', () => {
      currentSrc = img.src;
      currentName = img.getAttribute('alt') || 'qrcode';
      lbImg.src = currentSrc;
      lbImg.alt = currentName;
      overlay.hidden = false;
    });
  });
}

/**
 * Programmatic image download via fetch -> blob -> Object URL.
 * Avoids Cross-Origin restrictions because the image lives on our own origin.
 */
async function downloadImage(src, name) {
  try {
    const res = await fetch(src);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const ext = (blob.type.split('/')[1] || 'png').split(';')[0];
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.${ext}`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  } catch (_err) {
    alert('图片下载失败，请稍后重试或长按图片保存到相册。');
  }
}
