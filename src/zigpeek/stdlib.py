"""Markdown rendering against the autodoc WASM exports.

Smoke tests catch structural drift; cosmetic whitespace differences are
acceptable.
"""

from zigpeek.wasm import WasmStd

CAT_NAMESPACE = 0
CAT_CONTAINER = 1
CAT_GLOBAL_VARIABLE = 2
CAT_FUNCTION = 3
CAT_PRIMITIVE = 4
CAT_ERROR_SET = 5
CAT_GLOBAL_CONST = 6
CAT_ALIAS = 7
CAT_TYPE = 8
CAT_TYPE_TYPE = 9
CAT_TYPE_FUNCTION = 10


def render_search(std: WasmStd, query: str, limit: int = 20) -> str:
    ignore_case = query.lower() == query
    results = std.execute_query(query, ignore_case)

    md = f'# Search Results\n\nQuery: "{query}"\n\n'
    if results:
        limited = results[:limit]
        md += f"Found {len(results)} results (showing {len(limited)}):\n\n"
        for match in limited:
            md += f"- {std.fully_qualified_name(match)}\n"
    else:
        md += "No results found."
    return md


def render_get_item(std: WasmStd, name: str, get_source_file: bool = False) -> str:
    decl_index = std.find_decl(name)
    if decl_index is None:
        return f'# Error\n\nDeclaration "{name}" not found.'

    if get_source_file:
        cur = decl_index
        seen: set[int] = set()
        while True:
            cat = std.categorize_decl(cur, 0)
            if cat != CAT_ALIAS or cur in seen:
                break
            seen.add(cur)
            nxt = std.get_aliasee()
            if nxt is None or nxt == cur:
                break
            cur = nxt

        file_path = std.decl_file_path(cur)
        if file_path:
            file_decl = std.find_file_root(file_path)
            if file_decl is not None:
                return f"# {file_path}\n\n{std.decl_source_html(file_decl)}"
        return f'# Error\n\nCould not find source file for "{name}".'

    return _render_decl(std, decl_index)


def _render_decl(std: WasmStd, decl_index: int) -> str:
    current = decl_index
    seen: set[int] = set()
    while True:
        category = std.categorize_decl(current, 0)
        if category in (CAT_NAMESPACE, CAT_CONTAINER):
            return _render_namespace(std, current)
        if category in (
            CAT_GLOBAL_VARIABLE,
            CAT_PRIMITIVE,
            CAT_GLOBAL_CONST,
            CAT_TYPE,
            CAT_TYPE_TYPE,
        ):
            return _render_global(std, current)
        if category == CAT_FUNCTION:
            return _render_function(std, current)
        if category == CAT_TYPE_FUNCTION:
            return _render_type_function(std, current)
        if category == CAT_ERROR_SET:
            return _render_error_set(std, current)
        if category == CAT_ALIAS:
            if current in seen:
                return _render_not_found()
            seen.add(current)
            aliasee = std.get_aliasee()
            if aliasee is None:
                return _render_not_found()
            current = aliasee
            continue
        raise RuntimeError(f"unrecognized category {category}")


def _render_namespace(std: WasmStd, decl_index: int) -> str:
    name = std.decl_category_name(decl_index)
    md = f"# {name}\n\n"

    docs = std.decl_docs_html(decl_index, False)
    if docs:
        md += docs + "\n\n"

    members = std.namespace_members(decl_index, False)
    fields = std.decl_fields(decl_index)
    md += _render_namespace_md(std, decl_index, members, fields)
    return md


def _render_function(std: WasmStd, decl_index: int) -> str:
    name = std.decl_category_name(decl_index)
    md = f"# {name}\n"

    docs = std.decl_docs_html(decl_index, False)
    if docs:
        md += "\n" + docs

    proto = std.decl_fn_proto_html(decl_index, False)
    if proto:
        md += "\n\n## Function Signature\n\n" + proto

    params = std.decl_params(decl_index)
    if params:
        md += "\n\n## Parameters\n"
        for p in params:
            md += "\n" + std.decl_param_html(decl_index, p)

    err_set_node = std.fn_error_set(decl_index)
    if err_set_node is not None:
        base_decl = std.fn_error_set_decl(decl_index, err_set_node)
        error_list = std.error_set_node_list(decl_index, err_set_node)
        if error_list:
            md += "\n\n## Errors\n"
            for e in error_list:
                md += "\n" + std.error_html(base_decl, e)

    doctest = std.decl_doctest_html(decl_index)
    if doctest:
        md += "\n\n## Example Usage\n\n" + doctest

    source = std.decl_source_html(decl_index)
    if source:
        md += "\n\n## Source Code\n\n" + source

    return md


def _render_global(std: WasmStd, decl_index: int) -> str:
    name = std.decl_category_name(decl_index)
    md = f"# {name}\n\n"

    docs = std.decl_docs_html(decl_index, True)
    if docs:
        md += docs + "\n\n"

    source = std.decl_source_html(decl_index)
    if source:
        md += "## Source Code\n\n" + source + "\n\n"

    return md


def _render_type_function(std: WasmStd, decl_index: int) -> str:
    name = std.decl_category_name(decl_index)
    md = f"# {name}\n\n"

    docs = std.decl_docs_html(decl_index, False)
    if docs:
        md += docs + "\n\n"

    params = std.decl_params(decl_index)
    if params:
        md += "## Parameters\n\n"
        for p in params:
            md += std.decl_param_html(decl_index, p) + "\n\n"

    doctest = std.decl_doctest_html(decl_index)
    if doctest:
        md += "## Example Usage\n\n" + doctest + "\n\n"

    members = std.type_fn_members(decl_index, False)
    fields = std.type_fn_fields(decl_index)
    if members or fields:
        md += _render_namespace_md(std, decl_index, members, fields)
    else:
        source = std.decl_source_html(decl_index)
        if source:
            md += "## Source Code\n\n" + source + "\n\n"

    return md


def _render_error_set(std: WasmStd, decl_index: int) -> str:
    name = std.decl_category_name(decl_index)
    md = f"# {name}\n\n"

    docs = std.decl_docs_html(decl_index, False)
    if docs:
        md += docs + "\n\n"

    error_list = std.decl_error_set(decl_index)
    if error_list:
        md += "## Errors\n\n"
        for e in error_list:
            md += std.error_html(decl_index, e) + "\n\n"

    return md


def _render_not_found() -> str:
    return "# Error\n\nDeclaration not found."


def _render_namespace_md(
    std: WasmStd,
    base_decl: int,
    members: list[int],
    fields: list[int],
) -> str:
    types_list: list[tuple[int, int]] = []
    namespaces_list: list[tuple[int, int]] = []
    err_sets_list: list[tuple[int, int]] = []
    fns_list: list[int] = []
    vars_list: list[int] = []
    vals_list: list[tuple[int, int]] = []

    for original in members:
        member = original
        seen: set[int] = set()
        while True:
            cat = std.categorize_decl(member, 0)
            if cat == CAT_NAMESPACE:
                namespaces_list.append((original, member))
            elif cat == CAT_CONTAINER:
                types_list.append((original, member))
            elif cat == CAT_GLOBAL_VARIABLE:
                vars_list.append(member)
            elif cat == CAT_FUNCTION:
                fns_list.append(member)
            elif cat in (CAT_TYPE, CAT_TYPE_TYPE, CAT_TYPE_FUNCTION):
                types_list.append((original, member))
            elif cat == CAT_ERROR_SET:
                err_sets_list.append((original, member))
            elif cat in (CAT_GLOBAL_CONST, CAT_PRIMITIVE):
                vals_list.append((original, member))
            elif cat == CAT_ALIAS:
                if member in seen:
                    vals_list.append((original, member))
                    break
                seen.add(member)
                nxt = std.get_aliasee()
                if nxt is None:
                    vals_list.append((original, member))
                    break
                member = nxt
                continue
            else:
                raise RuntimeError(f"unknown category: {cat}")
            break

    md = ""

    if types_list:
        md += "## Types\n\n"
        for original, _ in types_list:
            md += f"- {std.decl_name(original)}\n"
        md += "\n"

    if namespaces_list:
        md += "## Namespaces\n\n"
        for original, _ in namespaces_list:
            md += f"- {std.decl_name(original)}\n"
        md += "\n"

    if err_sets_list:
        md += "## Error Sets\n\n"
        for original, _ in err_sets_list:
            md += f"- {std.decl_name(original)}\n"
        md += "\n"

    if fns_list:
        md += "## Functions\n\n"
        for decl in fns_list:
            name = std.decl_name(decl)
            proto = std.decl_fn_proto_html(decl, True)
            docs = std.decl_docs_html(decl, True)
            md += f"### {name}\n\n"
            if proto:
                md += proto + "\n\n"
            if docs:
                md += docs + "\n\n"

    if fields:
        md += "## Fields\n\n"
        for f in fields:
            md += std.decl_field_html(base_decl, f) + "\n\n"

    if vars_list:
        md += "## Global Variables\n\n"
        for decl in vars_list:
            name = std.decl_name(decl)
            type_html = std.decl_type_html(decl)
            docs = std.decl_docs_html(decl, True)
            md += f"### {name}\n\n"
            if type_html:
                md += f"Type: {type_html}\n\n"
            if docs:
                md += docs + "\n\n"

    if vals_list:
        md += "## Values\n\n"
        for original, member in vals_list:
            name = std.decl_name(original)
            type_html = std.decl_type_html(member)
            docs = std.decl_docs_html(member, True)
            md += f"### {name}\n\n"
            if type_html:
                md += f"Type: {type_html}\n\n"
            if docs:
                md += docs + "\n\n"

    return md
