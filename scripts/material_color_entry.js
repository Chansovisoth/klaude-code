// Maintenance entry point. Google Material Color Utilities, Apache-2.0.
// Bundled with esbuild; the browser performs no module/network dependency reads.
import {
  Hct, SchemeTonalSpot, SchemeExpressive, SchemeFidelity, SchemeContent,
  SchemeMonochrome, SchemeNeutral, SchemeVibrant, SchemeRainbow, SchemeFruitSalad,
  argbFromHex, argbFromRgb, hexFromArgb, QuantizerCelebi, Score, TonalPalette,
} from '@material/material-color-utilities';
window.MaterialColors = Object.freeze({
  Hct, argbFromHex, argbFromRgb, hexFromArgb, QuantizerCelebi, Score, TonalPalette,
  variants: Object.freeze({ 'tonal-spot': SchemeTonalSpot, expressive: SchemeExpressive,
    fidelity: SchemeFidelity, content: SchemeContent, monochrome: SchemeMonochrome,
    neutral: SchemeNeutral, vibrant: SchemeVibrant, rainbow: SchemeRainbow,
    'fruit-salad': SchemeFruitSalad }),
});
