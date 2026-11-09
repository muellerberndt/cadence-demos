// The look-ahead's own thread, so the page keeps drawing while it searches.
// In: {id, grid, heads, headings, prior, maxDepth, budgetMs, bonus}. Out: {id, move, values, depth, ms, nodes}.
import { Search } from "./search.js";

const search = new Search(24);
self.onmessage = (event) => {
  const { id, grid, heads, headings, prior, maxDepth, budgetMs, bonus } = event.data;
  const out = search.decide(grid, heads, headings, 0, { maxDepth, budgetMs, prior, bonus });
  self.postMessage({ id, ...out });
};
