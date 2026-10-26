/* Small typed form renderer for the live engine JSON Schema; no scientific defaults. */
const el = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
export function schemaField(definition, root, initial, label = "Evidence") {
  let schema = definition;
  if (schema.$ref) schema = root.$defs[schema.$ref.split("/").at(-1)];
  if (!schema) throw new Error(`Schema unavailable: ${label}`);
  const host = el("fieldset"), legend = el("legend", label); host.append(legend);
  if (schema.description) host.append(el("p", schema.description));
  let read;
  const choices = schema.oneOf || schema.anyOf;
  if (choices) {
    const select = el("select"), content = el("div");
    choices.forEach((choice, i) => { const o = el("option", choice.title || choice.$ref?.split("/").at(-1) || choice.type || `Option ${i + 1}`); o.value = String(i); select.append(o); });
    let index = choices.findIndex(c => initial === null ? c.type === "null" : initial !== undefined && c.type === typeof initial);
    if (index < 0) index = choices.findIndex(c => c.type !== "null"); select.value = String(Math.max(0, index));
    let field;
    const update = value => { field = schemaField(choices[Number(select.value)], root, value, label); content.replaceChildren(field.host); };
    update(initial); select.onchange = () => update(undefined); host.append(select, content); read = () => field.read();
  } else if ("const" in schema) { host.append(el("span", String(schema.const))); read = () => schema.const;
  } else if (schema.enum) {
    const select = el("select"), empty = el("option", "Select a value"); empty.value = ""; select.append(empty); select.required = true;
    schema.enum.forEach((value, i) => { const o = el("option", String(value)); o.value = String(i); select.append(o); });
    const found = schema.enum.indexOf(initial); if (found >= 0) select.value = String(found);
    host.append(select); read = () => { if (!select.reportValidity()) throw new Error(`Select ${label}`); return schema.enum[Number(select.value)]; };
  } else if (schema.type === "null") { host.append(el("span", "Not supplied")); read = () => null;
  } else if (schema.type === "object" || schema.properties) {
    const fields = [];
    for (const [key, property] of Object.entries(schema.properties || {})) {
      const required = schema.required?.includes(key), value = initial?.[key], holder = el("div");
      let field = null, enabled = required || value !== undefined;
      const mount = () => { field = schemaField(property, root, value, key); holder.replaceChildren(field.host); };
      if (!required) {
        const check = el("input"); check.type = "checkbox"; check.checked = enabled;
        const wrap = el("label", `Include ${key}`); wrap.append(check); host.append(wrap);
        check.onchange = () => { enabled = check.checked; if (enabled && !field) mount(); holder.hidden = !enabled; };
      }
      if (enabled) mount(); holder.hidden = !enabled; host.append(holder);
      fields.push({key, read: () => enabled ? field.read() : ("default" in property ? structuredClone(property.default) : undefined)});
    }
    read = () => Object.fromEntries(fields.map(f => [f.key, f.read()]).filter(([, v]) => v !== undefined));
  } else if (schema.type === "array") {
    const list = el("div"), fields = [];
    const add = value => {
      const row = el("div"), field = schemaField(schema.items, root, value, "Item"), remove = el("button", "Remove"); remove.type = "button";
      const record = {row, field}; remove.onclick = () => { fields.splice(fields.indexOf(record), 1); row.remove(); };
      fields.push(record); row.append(field.host, remove); list.append(row);
    };
    (initial || []).forEach(add); const button = el("button", "Add item"); button.type = "button"; button.onclick = () => add(undefined); host.append(list, button); read = () => fields.map(f => f.field.read());
  } else {
    const input = el("input"); input.setAttribute("aria-label", label);
    if (schema.type === "boolean") {
      // A select keeps absent/false separate when nested in an optional field.
      const select = el("select"), empty = el("option", "Select true or false"); empty.value = ""; select.append(empty); select.required = true;
      [true, false].forEach(v => { const o = el("option", String(v)); o.value = String(v); select.append(o); }); select.value = initial === undefined ? "" : String(initial); host.append(select); read = () => { if (!select.reportValidity()) throw new Error(`Select ${label}`); return select.value === "true"; };
    } else {
      input.type = ["integer", "number"].includes(schema.type) ? "number" : "text";
      if (input.type === "number") { input.step = schema.type === "integer" ? "1" : "any"; if (schema.minimum !== undefined) input.min = schema.minimum; if (schema.maximum !== undefined) input.max = schema.maximum; }
      input.value = initial ?? ""; input.required = true;
      if (schema.minLength) input.minLength = schema.minLength; if (schema.maxLength) input.maxLength = schema.maxLength;
      host.append(input); read = () => { if (!input.reportValidity()) throw new Error(`Invalid ${label}`); return input.type === "number" ? Number(input.value) : input.value; };
    }
  }
  return {host, read};
}
