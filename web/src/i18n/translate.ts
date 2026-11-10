import { currentLang } from "./lang";

/**
 * Persian for the whole interface. The screens are written in English; in Persian mode every piece of interface text (text nodes and the
 * placeholder / aria-label / title / alt attributes) is looked up in a dictionary and replaced in place, and digits become Persian digits.
 * Text the person or the AI wrote (chat messages, titles, file names) is never in the dictionary, so it is never touched.
 */
type Rule = [RegExp, (...match: string[]) => string];
const ATTRIBUTES = ["placeholder", "aria-label", "title", "alt"] as const;
const SKIP = "script,style,textarea,pre,code,[data-no-translate],[contenteditable='true'],svg text";
const DIGITS = "۰۱۲۳۴۵۶۷۸۹";

let dictionary: Record<string, string> = Object.create(null);
let rules: Rule[] = [];
const faDigits = (text: string) => text.replace(/\d/g, digit => DIGITS[Number(digit)]);
const hasWordLatin = (text: string) => /[A-Za-z]{3,}/.test(text);

export function translateText(text: string): string {
  const core = text.trim();
  if (!core) return text;
  let out = Object.prototype.hasOwnProperty.call(dictionary, core) ? dictionary[core] : undefined;       // a text such as "constructor" must not find Object.prototype's member
  if (out === undefined) {
    for (const [pattern, replace] of rules) {
      const found = core.match(pattern);
      if (found) { out = replace(...found.slice(1)); break; }
    }
  }
  if (out === undefined) out = hasWordLatin(core) ? core : faDigits(core);           // names, ids and file names keep their digits
  else out = faDigits(out);
  return out === core ? text : text.replace(core, out);
}

function skipped(node: Node): boolean {
  const element = node.nodeType === 1 ? (node as Element) : node.parentElement;
  return !element || Boolean(element.closest(SKIP));
}

function translateNode(node: Node) {
  try { translateNodeUnsafe(node); } catch (error) { if (typeof console !== "undefined") console.warn("translation skipped a node", error); }
}

function translateNodeUnsafe(node: Node) {
  if (node.nodeType === 3) {
    if (skipped(node)) return;
    const value = node.nodeValue || "";
    const next = translateText(value);
    if (next !== value) node.nodeValue = next;
    return;
  }
  if (node.nodeType !== 1) return;
  const element = node as Element;
  if (element.closest("script,style,[data-no-translate]")) return;
  for (const name of ATTRIBUTES) {                         // a textarea's placeholder is interface text even though its content is not
    const value = element.getAttribute(name);
    if (value) { const next = translateText(value); if (next !== value) element.setAttribute(name, next); }
  }
  if (element.closest(SKIP)) return;
  element.childNodes.forEach(translateNode);
}

export async function startTranslator() {
  if (currentLang() !== "fa") return;
  let module: typeof import("./fa");
  try { module = await import("./fa"); } catch (error) { console.warn("the Persian dictionary could not be loaded", error); return; }
  dictionary = Object.assign(Object.create(null), module.FA);
  rules = module.RULES;
  const root = document.body;
  const pending = new Set<Node>();
  let scheduled = false;
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === "childList") record.addedNodes.forEach(node => pending.add(node));
      else pending.add(record.target);
    }
    if (scheduled) return;
    scheduled = true;
    window.setTimeout(() => {              // not requestAnimationFrame: it does not run in a hidden tab, and the text must already be Persian when the tab is shown
      scheduled = false;
      observer.disconnect();
      try {
        pending.forEach(node => { if (node.isConnected) translateNode(node); });
      } finally {                          // whatever happens, the observer is attached again and the queue is emptied
        pending.clear();
        observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: [...ATTRIBUTES] });
      }
    }, 16);
  });
  translateNode(root);
  observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: [...ATTRIBUTES] });
  document.title = translateText(document.title);
}
