var top_idx = 1;
var markTag = null;
function showtab(tabname) {
    document.getElementById(tabname).style.zIndex = ++top_idx;
}
function markTagReset() {
    if(markTag) markTag.replaceWith(...markTag.childNodes);
    markTag = document.createElement("mark");
}
function skipToChar(node, i) {
    // Skip to node that contains ith character.
    // Returns node, and char index relative to found node
    if(node == null) {
        return [null, i];
    } else if(node.nodeType == Node.TEXT_NODE) {
         if(i >= node.length) return skipToChar(node.nextSibling, i-node.length);
         else return [node, i];
    } else {
        let subnode = null;
        if(node.childNodes) [subnode, i] = skipToChar(node.childNodes[0], i);

        if(subnode == null || subnode.nodeType != Node.TEXT_NODE || i >= subnode.length) {
            // childlist didn't suffice, try siblings
            return skipToChar(node.nextSibling, i);
        } else {
            return [subnode, i];
        }
    }
}
function highlight_file(name, first_row, first_col, last_row, end_col) {
    showtab(name);
    markTagReset();
    const range = document.createRange();

    const [startNode, startOffset] = skipToChar(document.getElementById(name + ":" + first_row).nextSibling, first_col-1)
    range.setStart(startNode, startOffset)
    const [endNode, endOffset] = skipToChar(document.getElementById(name + ":" + last_row).nextSibling, end_col-1)
    range.setEnd(endNode, endOffset)

    range.surroundContents(markTag);
}
