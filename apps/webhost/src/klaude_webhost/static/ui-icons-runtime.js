/* Local UI icons. Font Awesome Free Solid attribution: icons/ui/LICENSE.txt.
 * Use semantic names from icons/ui/registry.json; specialty icons are data-only.
 */
window.KlaudeUIIcons = (() => {
  const {glyphs, aliases, custom} = window.KlaudeUIIconData;
  const namespace = 'http://www.w3.org/2000/svg';
  function definition(name) {
    if (Object.hasOwn(custom, name)) return {...custom[name], source:'custom', name};
    const resolved = Object.hasOwn(aliases, name) ? aliases[name] : name;
    const glyph = Object.hasOwn(glyphs, resolved) ? glyphs[resolved] : glyphs.file;
    return {viewBox:[0, 0, glyph[0], glyph[1]], path:glyph[2],
      source:'fontawesome-free-solid', name:Object.hasOwn(glyphs, resolved) ? resolved : 'file'};
  }
  function render(svg, name) {
    const icon = definition(name);
    svg.setAttribute('viewBox', icon.viewBox.join(' '));
    svg.setAttribute('fill', 'currentColor'); svg.setAttribute('stroke', 'none');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('data-ui-icon', name);
    svg.setAttribute('data-icon-source', icon.source);
    svg.setAttribute('data-icon-name', icon.name);
    svg.classList.add('ui-icon');
    const path = document.createElementNS(namespace, 'path');
    path.setAttribute('d', icon.path); path.setAttribute('fill', 'currentColor');
    svg.replaceChildren(path);
    return svg;
  }
  function create(name) {
    const svg = document.createElementNS(namespace, 'svg');
    svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
    return render(svg, name);
  }
  function decorate(root = document) {
    for (const svg of root.querySelectorAll('svg[data-ui-icon]')) render(svg, svg.dataset.uiIcon);
  }
  decorate();
  return Object.freeze({create, render, decorate, definition, names:Object.freeze(Object.keys(aliases))});
})();
