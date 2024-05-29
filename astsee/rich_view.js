let topIdx = 1;
let astTab = null; // we don't set it at start to avoid race (js may start before content load)
let gotoIdx = 0; // idx for producing unique ids for gotoClassInAst()

function showtab(tabname, updateMenu=true, tabmenuId='src-tabmenu') {
  if (updateMenu) document.getElementById(tabmenuId).value = tabname;
  tab = document.getElementById(tabname);
  if (tabmenuId == 'ast-tabmenu') astTab = tab;
  tab.style.zIndex = ++topIdx;
  tab.style.display = 'block';
}

/* exported gotoClassInAst */
function gotoClassInAst(cls) {
// go to first occurence of class inside curent AST tab (emulate link to id)
  if (astTab == null) astTab = document.querySelector('.ast-pane .tab'); // first tab is default one
  const elem = astTab.getElementsByClassName(cls)[0];
  if (!elem.hasAttribute('id')) { // if no id already, assign arbitrary one
    elem.id = 'goto-idx-' + (gotoIdx++);
  }
  window.location.href = '#' + elem.id;
  return false; // prevent default action (going to href) of <a href="..." onclick=goto...">
}

function skipToChar(node, i) {
  // Skip to node that contains ith character.
  // Returns node, and char index relative to found node
  if (node == null) {
    return [null, i];
  } else if (node.nodeType == Node.TEXT_NODE) {
    if (i >= node.length) return skipToChar(node.nextSibling, i-node.length);
    else return [node, i];
  } else {
    let subnode = null;
    if (node.childNodes) [subnode, i] = skipToChar(node.childNodes[0], i);

    if (subnode == null || subnode.nodeType != Node.TEXT_NODE || i >= subnode.length) {
      // childlist didn't suffice, try siblings
      return skipToChar(node.nextSibling, i);
    } else {
      return [subnode, i];
    }
  }
}
/* exported selectFileFragment */
function selectFileFragment(name, firstRow, firstCol, lastRow, endCol) {
  showtab(name);
  const range = document.createRange();
  const [startNode, startOffset] =
     skipToChar(document.getElementById(name + '-' + firstRow).nextSibling, firstCol-1);
  range.setStart(startNode, startOffset);
  const [endNode, endOffset] =
     skipToChar(document.getElementById(name + '-' + lastRow).nextSibling, endCol-1);
  range.setEnd(endNode, endOffset);

  // going to href would clear selection in firefox, so it should be done first
  window.location.href = '#' + name + '-' + firstRow;
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  return false; // prevent default action (going to href) of <a href="..." onclick="return selectFileFragment(...)">
}
