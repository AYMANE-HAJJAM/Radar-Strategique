// Keep a snapshot of the results view in history URLs, including pagination and filters.
export function radarNavigation(search: URLSearchParams) {
  const history = search.get("view") === "history";
  const results = new URLSearchParams(history ? search.get("return") || "status=pending" : search);
  results.delete("view");
  results.delete("return");
  const historyHref = "?" + new URLSearchParams({ view: "history", return: results.toString() });
  function tabHref(status: string) {
    const params = new URLSearchParams(results);
    if ((params.get("status") || "pending") !== status) params.delete("page");
    params.set("status", status);
    if (status !== "pending") {
      const selected = params.get("run_id");
      if (selected) params.set("focus", selected);
      params.delete("run_id");
    }
    return "?" + params;
  }
  return { history, historyHref, tabHref };
}
