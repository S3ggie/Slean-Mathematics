import Mathlib
import Lean

open Lean Elab Command Meta

syntax "#slean_export_registry" : command

elab_rules : command
  | `(#slean_export_registry) => do
      let env ← getEnv
      let sorted := (env.constants.toList.map (fun pair => (pair.1.toString, pair))
        |>.toArray.qsort (fun left right => left.1 < right.1)).toList
      let requiredNames := ["Nat.Prime", "Ideal.IsPrime"]
      let sampled := sorted.filter (fun pair => !requiredNames.contains pair.1) |>.take 5000
      let required := sorted.filter (fun pair => requiredNames.contains pair.1)
      for (nameString, (_name, info)) in sampled ++ required do
        let type ← liftTermElabM do ppExpr info.type
        let row := Json.mkObj [
          ("id", Json.str s!"mathlib.{nameString}"),
          ("lean_name", Json.str nameString),
          ("lean_type", Json.str type.pretty),
          ("source", Json.mkObj [
            ("kind", Json.str "environment"),
            ("revision", Json.str "leanprover/lean4:v4.34.0-rc2"),
            ("mathlib_revision", Json.str "70f3f13433ba3d82a15a7cae679abac9128f102b")
          ])
        ]
        liftIO <| IO.println row.compress

#slean_export_registry
