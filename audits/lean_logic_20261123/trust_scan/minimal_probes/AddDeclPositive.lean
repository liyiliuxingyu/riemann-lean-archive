import Lean
open Lean Elab Command
elab "audit_add_valid_thm" : command => liftCoreM do
  addDecl (.thmDecl { name := `audit_valid_added_thm, levelParams := [], type := mkConst ``True, value := mkConst ``True.intro })
audit_add_valid_thm
