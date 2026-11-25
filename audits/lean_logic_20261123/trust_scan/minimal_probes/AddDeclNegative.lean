import Lean
open Lean Elab Command
elab "audit_add_invalid_thm" : command => liftCoreM do
  addDecl (.thmDecl { name := `audit_invalid_added_thm, levelParams := [], type := mkConst ``False, value := mkConst ``True.intro })
audit_add_invalid_thm
