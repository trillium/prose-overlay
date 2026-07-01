"use strict";
(() => {
  // packages/cursorless-engine/src/actions/proseShim.ts
  var ProsePosition = class _ProsePosition {
    constructor(line, character) {
      this.line = line;
      this.character = character;
    }
    isEqual(other) {
      return this.line === other.line && this.character === other.character;
    }
    isBefore(other) {
      return this.line < other.line || this.line === other.line && this.character < other.character;
    }
    translate(lineDelta, characterDelta) {
      return new _ProsePosition(this.line + lineDelta, this.character + characterDelta);
    }
    toJSON() {
      return { line: this.line, character: this.character };
    }
  };
  var ProseRange = class _ProseRange {
    constructor(startOrRange, end) {
      if (startOrRange instanceof _ProseRange) {
        this.start = startOrRange.start;
        this.end = startOrRange.end;
      } else {
        this.start = startOrRange;
        this.end = end;
      }
    }
    get isEmpty() {
      return this.start.isEqual(this.end);
    }
    contains(posOrRange) {
      if (posOrRange instanceof ProsePosition) {
        return !posOrRange.isBefore(this.start) && !this.end.isBefore(posOrRange);
      }
      return this.contains(posOrRange.start) && this.contains(posOrRange.end);
    }
    toSelection(isReversed) {
      return isReversed ? new ProseSelection(this.end, this.start) : new ProseSelection(this.start, this.end);
    }
    toJSON() {
      return { start: this.start.toJSON(), end: this.end.toJSON() };
    }
  };
  var ProseSelection = class extends ProseRange {
    constructor(anchor, active) {
      const reversed = active.isBefore(anchor);
      super(reversed ? active : anchor, reversed ? anchor : active);
      this.anchor = anchor;
      this.active = active;
      this.isReversed = reversed;
    }
    toJSON() {
      return { anchor: this.anchor.toJSON(), active: this.active.toJSON() };
    }
  };
  var ProseTextEditorEdit = class {
    constructor() {
      this.ops = [];
    }
    delete(range) {
      this.ops.push({ type: "delete", range });
    }
    insert(position, text) {
      this.ops.push({ type: "insert", position, text });
    }
    replace(range, text) {
      this.ops.push({ type: "replace", range, text });
    }
  };
  var ProseTextLine = class {
    constructor(text, lineNumber) {
      this.text = text;
      this.lineNumber = lineNumber;
    }
    get range() {
      return new ProseRange(
        new ProsePosition(this.lineNumber, 0),
        new ProsePosition(this.lineNumber, this.text.length)
      );
    }
    get rangeIncludingLineBreak() {
      return this.range;
    }
  };
  var ProseTextDocument = class {
    constructor(text) {
      this.text = text;
      this.lineCount = 1;
      this.uri = { toString: () => "prose://overlay" };
      this.languageId = "plaintext";
      this.version = 1;
      this.isDirty = false;
    }
    getText(range) {
      if (range == null)
        return this.text;
      const start = this.offsetAt(range.start);
      const end = this.offsetAt(range.end);
      return this.text.slice(start, end);
    }
    lineAt(lineOrPos) {
      return new ProseTextLine(this.text, 0);
    }
    offsetAt(pos) {
      return Math.min(pos.character, this.text.length);
    }
    positionAt(offset) {
      return new ProsePosition(0, Math.min(offset, this.text.length));
    }
    validatePosition(pos) {
      return new ProsePosition(
        Math.max(0, Math.min(pos.line, 0)),
        Math.max(0, Math.min(pos.character, this.text.length))
      );
    }
    validateRange(range) {
      return new ProseRange(
        this.validatePosition(range.start),
        this.validatePosition(range.end)
      );
    }
  };
  var ProseTextEditor = class {
    constructor(text, selection) {
      this._editOps = [];
      this._newSelections = null;
      this.document = new ProseTextDocument(text);
      this.selections = [selection];
    }
    /** Simulate editor.edit(callback) — creates an edit builder, calls callback, records ops. */
    async edit(callback) {
      const builder = new ProseTextEditorEdit();
      callback(builder);
      this._editOps.push(...builder.ops);
      return true;
    }
    /** Simulate editor.setSelections(selections) — records new selections. */
    setSelections(selections) {
      this._newSelections = [...selections];
    }
    /** Simulate editableEditor.setSelections (VS Code EditableTextEditor compat) */
    async setSelectionsAsync(selections) {
      this._newSelections = [...selections];
    }
    /** Return the recorded edit plan. */
    getPlan() {
      return {
        edits: this._editOps,
        newSelections: this._newSelections ?? this.selections
      };
    }
    // ---------------------------------------------------------------------------
    // VS Code EditableTextEditor compatibility surface
    // (these are the methods called by setSelectionsAndFocusEditor etc.)
    // ---------------------------------------------------------------------------
    /** Focus simulation — no-op in shim */
    focus() {
    }
    /** revealRange — no-op in shim */
    revealRange(_range, _revealType) {
    }
  };
  function posFromObj(obj) {
    return new ProsePosition(obj.line, obj.character);
  }
  function rangeFromObj(obj) {
    return new ProseRange(posFromObj(obj.start), posFromObj(obj.end));
  }

  // packages/cursorless-engine/src/actions/proseActionsStandalone.ts
  function makeEditor(doc) {
    const anchor = new ProsePosition(0, doc.selectionAnchorChar);
    const active = new ProsePosition(0, doc.selectionActiveChar);
    return new ProseTextEditor(doc.text, new ProseSelection(anchor, active));
  }
  function actionRemove(target, editor) {
    const range = rangeFromObj(target.contentRange);
    editor.edit((b) => b.delete(range));
    const collapsed = new ProseSelection(range.start, range.start);
    editor.setSelections([collapsed]);
    return editor.getPlan();
  }
  function actionSetSelection(target, editor) {
    const range = rangeFromObj(target.contentRange);
    const sel = range.toSelection(target.isReversed);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function actionClearAndSetSelection(target, editor) {
    const range = rangeFromObj(target.contentRange);
    editor.edit((b) => b.delete(range));
    const collapsed = new ProseSelection(range.start, range.start);
    editor.setSelections([collapsed]);
    return editor.getPlan();
  }
  function actionReplaceWithTarget(source, destination, editor) {
    const srcRange = rangeFromObj(source.contentRange);
    const dstRange = rangeFromObj(destination.contentRange);
    const srcText = editor.document.getText(srcRange);
    editor.edit((b) => b.replace(dstRange, srcText));
    const sel = new ProseSelection(dstRange.start, dstRange.start);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function actionMoveToTarget(source, destination, editor) {
    const srcRange = rangeFromObj(source.contentRange);
    const dstRange = rangeFromObj(destination.contentRange);
    const srcText = editor.document.getText(srcRange);
    editor.edit((b) => {
      b.replace(dstRange, srcText);
      b.delete(srcRange);
    });
    const sel = new ProseSelection(dstRange.start, dstRange.start);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function actionSetSelectionBefore(target, editor) {
    const pos = posFromObj(target.contentRange.start);
    editor.setSelections([new ProseSelection(pos, pos)]);
    return editor.getPlan();
  }
  function actionSetSelectionAfter(target, editor) {
    const pos = posFromObj(target.contentRange.end);
    editor.setSelections([new ProseSelection(pos, pos)]);
    return editor.getPlan();
  }
  function actionInsertCopyBefore(target, editor) {
    const range = rangeFromObj(target.contentRange);
    const srcText = editor.document.getText(range);
    editor.edit((b) => b.insert(range.start, srcText + " "));
    const sel = new ProseSelection(range.start, range.start);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function actionInsertCopyAfter(target, editor) {
    const range = rangeFromObj(target.contentRange);
    const srcText = editor.document.getText(range);
    editor.edit((b) => b.insert(range.end, " " + srcText));
    const insertedStart = new ProsePosition(
      range.end.line,
      range.end.character + 1
    );
    const sel = new ProseSelection(insertedStart, insertedStart);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function actionReverse(targets, editor) {
    if (targets.length === 0) {
      editor.setSelections([]);
      return editor.getPlan();
    }
    const sorted = [...targets].sort(
      (a, b) => a.contentRange.start.character - b.contentRange.start.character
    );
    const ranges = sorted.map((t) => rangeFromObj(t.contentRange));
    const texts = ranges.map((r) => editor.document.getText(r));
    const reversed = [...texts].reverse();
    editor.edit((b) => {
      for (let i = 0; i < ranges.length; i++) {
        b.replace(ranges[i], reversed[i]);
      }
    });
    const firstStart = ranges[0].start;
    const sel = new ProseSelection(firstStart, firstStart);
    editor.setSelections([sel]);
    return editor.getPlan();
  }
  function proseRunAction(actionNameJson, sourceTargetJson, destTargetJson, documentJson) {
    try {
      const actionName = JSON.parse(actionNameJson);
      const sourceRaw = JSON.parse(sourceTargetJson);
      const dest = JSON.parse(destTargetJson);
      const doc = JSON.parse(documentJson);
      const editor = makeEditor(doc);
      let plan;
      if (actionName === "reverseTargets") {
        if (!Array.isArray(sourceRaw)) {
          throw new Error(
            "reverseTargets requires an array of targets in the source slot"
          );
        }
        plan = actionReverse(sourceRaw, editor);
      } else {
        if (Array.isArray(sourceRaw)) {
          throw new Error(
            `Action '${actionName}' expects a single target, got an array`
          );
        }
        const source = sourceRaw;
        switch (actionName) {
          case "remove":
            plan = actionRemove(source, editor);
            break;
          case "setSelection":
            plan = actionSetSelection(source, editor);
            break;
          case "clearAndSetSelection":
            plan = actionClearAndSetSelection(source, editor);
            break;
          case "replaceWithTarget":
            if (dest == null) {
              throw new Error("replaceWithTarget requires a destination target");
            }
            plan = actionReplaceWithTarget(source, dest, editor);
            break;
          case "moveToTarget":
            if (dest == null) {
              throw new Error("moveToTarget requires a destination target");
            }
            plan = actionMoveToTarget(source, dest, editor);
            break;
          case "setSelectionBefore":
            plan = actionSetSelectionBefore(source, editor);
            break;
          case "setSelectionAfter":
            plan = actionSetSelectionAfter(source, editor);
            break;
          case "insertCopyBefore":
            plan = actionInsertCopyBefore(source, editor);
            break;
          case "insertCopyAfter":
            plan = actionInsertCopyAfter(source, editor);
            break;
          default:
            throw new Error(`Unknown action: ${actionName}`);
        }
      }
      return JSON.stringify(plan);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: msg });
    }
  }
  globalThis.proseRunAction = proseRunAction;
})();
