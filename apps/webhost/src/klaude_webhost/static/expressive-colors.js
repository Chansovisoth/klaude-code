"use strict";

// Klaude Expressive: independent browser adaptation of Material tonal roles.
// Color mathematics belongs to the locally bundled Google library (Apache-2.0).
window.KlaudeColors ??= (() => {
  const m = window.MaterialColors;
  const seeds = Object.freeze({ slate: '#777777', lavender: '#65558f', sage: '#43664e',
    peach: '#8b4e33', ocean: '#235d91', rose: '#914468', teal: '#006a68', amber: '#795900',
    crimson: '#98415a', coral: '#9c4430', violet: '#7b4397', indigo: '#515b96',
    emerald: '#006c48', lime: '#516523', sky: '#006780', cocoa: '#80543e' });
  const roles = ['primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer',
    'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
    'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
    'background', 'onBackground', 'surface', 'onSurface', 'surfaceDim', 'surfaceBright',
    'surfaceContainerLowest', 'surfaceContainerLow', 'surfaceContainer',
    'surfaceContainerHigh', 'surfaceContainerHighest', 'surfaceVariant', 'onSurfaceVariant',
    'outline', 'outlineVariant', 'inverseSurface', 'inverseOnSurface', 'inversePrimary',
    'error', 'onError', 'errorContainer', 'onErrorContainer', 'shadow', 'scrim', 'surfaceTint'];
  const cache = new Map();
  const kebab = name => name.replace(/[A-Z]/g, match => '-' + match.toLowerCase());
  function palette(value, dark) {
    const source = value.colorSource || 'preset';
    const seed = source === 'preset' ? seeds[value.palette] : value.accent;
    const variant = source === 'preset' && value.palette === 'slate' ? 'monochrome' : value.variant;
    const key = `${seed}/${variant}/${dark}`;
    if (cache.has(key)) return cache.get(key);
    const scheme = new (m.variants[variant] || m.variants['tonal-spot'])(
      m.Hct.fromInt(m.argbFromHex(seed || seeds.lavender)), dark, 0);
    const result = Object.fromEntries(roles.map(role => [kebab(role), m.hexFromArgb(scheme[role])]));
    // Success is a separate semantic palette, never a replacement for primary.
    const success = m.TonalPalette.fromHueAndChroma(150, 35);
    for (const [role, tone] of Object.entries(dark ?
      { success: 80, 'on-success': 20, 'success-container': 30, 'on-success-container': 90 } :
      { success: 40, 'on-success': 100, 'success-container': 90, 'on-success-container': 10 }))
      result[role] = m.hexFromArgb(success.tone(tone));
    if (cache.size >= 40) cache.delete(cache.keys().next().value);
    cache.set(key, result);
    return result;
  }
  function apply(value) {
    const dark = value.theme === 'dark' || value.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches;
    const root = document.documentElement, colors = palette(value, dark);
    for (const [role, color] of Object.entries(colors)) root.style.setProperty('--' + role, color);
    // Existing components keep their established role aliases.
    for (const [alias, role] of Object.entries({ muted: 'on-surface-variant',
      'surface-raised': 'surface-container-low', 'surface-high': 'surface-container-high' }))
      root.style.setProperty('--' + alias, colors[role]);
    root.style.setProperty('--surface-opacity', `${100 - (value.transparency || 0)}%`);
    root.style.colorScheme = dark ? 'dark' : 'light';
    root.dataset.colorSource = value.colorSource || 'preset';
    return colors;
  }
  async function fromImage(file) {
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 16 * 1024 * 1024)
      throw new Error('Choose a PNG, JPEG or WebP image up to 16 MiB.');
    // Decoding/downsampling and quantization remain on this device. Never upload.
    const image = await createImageBitmap(file, { resizeWidth: 96, resizeHeight: 96, resizeQuality: 'low' });
    try {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 96;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0, 96, 96);
      const data = context.getImageData(0, 0, 96, 96).data, pixels = [];
      for (let index = 0; index < data.length; index += 4)
        if (data[index + 3] >= 128) pixels.push(m.argbFromRgb(data[index], data[index + 1], data[index + 2]));
      if (!pixels.length) throw new Error('This image has no visible colors.');
      return m.hexFromArgb(m.Score.score(m.QuantizerCelebi.quantize(pixels, 64))[0]);
    } finally { image.close(); }
  }
  return Object.freeze({ seeds, palette, apply, fromImage });
})();
