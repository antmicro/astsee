let topIdx = 1;

function showtab(tabname) {
  document.getElementById(tabname).style.zIndex = ++topIdx;
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
     skipToChar(document.getElementById(name + '-' + firstRow).nextSibling.nextSibling, firstCol-1);
  range.setStart(startNode, startOffset);
  const [endNode, endOffset] =
     skipToChar(document.getElementById(name + '-' + lastRow).nextSibling.nextSibling, endCol-1);
  range.setEnd(endNode, endOffset);

  // going to href would clear selection in firefox, so it should be done first
  window.location.href = '#' + name + '-' + firstRow;
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  return false; // prevent default action (going to href) of <a href="..." onclick="return selectFileFragment(...)">
}
