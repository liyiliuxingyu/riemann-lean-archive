import Lean

open Lean

-- Only compiler hygiene on bound-variable names is erased. BinderInfo,
-- constants, levels, type structure, metadata, and user-visible names remain.
partial def eraseBinderHygiene : Expr → Expr
  | .forallE name type body info =>
    .forallE name.eraseMacroScopes (eraseBinderHygiene type) (eraseBinderHygiene body) info
  | .lam name type body info =>
    .lam name.eraseMacroScopes (eraseBinderHygiene type) (eraseBinderHygiene body) info
  | .letE name type value body nonDep =>
    .letE name.eraseMacroScopes (eraseBinderHygiene type) (eraseBinderHygiene value)
      (eraseBinderHygiene body) nonDep
  | .app fn arg => .app (eraseBinderHygiene fn) (eraseBinderHygiene arg)
  | .mdata data body => .mdata data (eraseBinderHygiene body)
  | .proj typeName idx value => .proj typeName idx (eraseBinderHygiene value)
  | other => other

-- Export the complete Lean.Expr constructor representation and universe parameters.
-- This intentionally does not pretty-print the theorem's surface type.
def main (args : List String) : IO UInt32 := do
  let moduleName :: names := args |
    throw <| IO.userError "usage: ExportApiTypes MODULE DECLARATION..."
  initSearchPath (← findSysroot)
  let env ← importModules #[{module := moduleName.toName}] {}
  for textName in names do
    let name := textName.toName
    let some info := env.find? name |
      throw <| IO.userError s!"declaration not found: {name}"
    let isTheorem := match info with
      | .thmInfo _ => true
      | _ => false
    IO.println <| (Json.mkObj [
      ("declaration", Json.str textName),
      ("type_expr", Json.str (reprStr info.type)),
      ("type_expr_bound_name_hygiene_erased", Json.str (reprStr (eraseBinderHygiene info.type))),
      ("level_parameters", Json.str (reprStr info.levelParams)),
      ("is_theorem", toJson isTheorem)]).compress
  return 0
