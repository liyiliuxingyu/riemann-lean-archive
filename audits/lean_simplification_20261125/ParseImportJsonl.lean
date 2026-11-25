import Lean.Elab.ParseImportsFast
import Lean.Data.Json

open Lean

-- Input: one JSON object per line with string fields "id" and "source".
-- Output: one JSON object per line with the same id and the official ModuleHeader.
-- Parses only the header; imports are not resolved, loaded, or elaborated.
def main : IO Unit := do
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let record ← IO.ofExcept (Json.parse line)
    let id ← IO.ofExcept (record.getObjValAs? String "id")
    let source ← IO.ofExcept (record.getObjValAs? String "source")
    let result ← try
      let header ← Lean.parseImports' source id
      pure <| Json.mkObj [("id", Json.str id), ("header", toJson header)]
    catch e =>
      pure <| Json.mkObj [("id", Json.str id), ("error", Json.str e.toString)]
    output.putStrLn result.compress
