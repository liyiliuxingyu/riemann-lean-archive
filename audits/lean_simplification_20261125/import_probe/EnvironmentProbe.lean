import Lean

open Lean

def main : IO Unit := do
  initSearchPath (← findSysroot)
  let before ← importModules #[{module := `Init}, {module := `Init},
    {module := `Std}, {module := `Std}] {}
  let after ← importModules #[{module := `Init}, {module := `Std}] {}
  unless before.allImportedModuleNames == after.allImportedModuleNames do
    throw <| IO.userError "effective imported module closure differs"
  let beforeConstants := before.constants.toList
  let afterConstants := after.constants.toList
  unless beforeConstants.length == afterConstants.length do
    throw <| IO.userError "constant counts differ"
  for (name, beforeInfo) in beforeConstants do
    let some afterInfo := after.find? name |
      throw <| IO.userError s!"missing declaration: {name}"
    unless beforeInfo.type == afterInfo.type &&
        beforeInfo.value? (allowOpaque := true) == afterInfo.value? (allowOpaque := true) &&
        beforeInfo.levelParams == afterInfo.levelParams do
      throw <| IO.userError s!"declaration differs: {name}"
  let axioms := beforeConstants.filterMap fun (name, info) =>
    match info with
    | .axiomInfo _ => some name.toString
    | _ => none
  IO.println s!"direct import entries: {before.imports.size} -> {after.imports.size}"
  IO.println s!"effective imported module closure: identical ({before.allImportedModuleNames.size} modules)"
  IO.println s!"imported declaration names, types, values and universe parameters: identical ({beforeConstants.length} declarations)"
  IO.println s!"imported axioms: {String.intercalate ", " (axioms.mergeSort (· < ·))}"
  IO.println "PASS: exact duplicates of ordinary imports have matching effective environments in this probe."
