import Mathlib
import Lean

open Lean Elab Command Meta

syntax "#slean_export_registry" : command

def stableRank (name : String) : Nat :=
  name.toList.foldl (fun hash character => (hash * 16777619 + character.toNat) % 18446744073709551616) 2166136261

elab_rules : command
  | `(#slean_export_registry) => do
      let env ← getEnv
      let mandatoryText ← liftIO <| IO.getEnv "SLEAN_MANDATORY_NAMES"
      let requiredNames := (mandatoryText.getD "").splitOn "," |>.filter (· != "")
      let constants := env.constants.toList
      let ranked := (constants.map (fun pair => (pair.1.toString, pair))
        |>.toArray.qsort (fun left right =>
          let leftRank := stableRank left.1
          let rightRank := stableRank right.1
          leftRank < rightRank || (leftRank == rightRank && left.1 < right.1))).toList
      let selected := ranked.take 5000
      let required := ranked.filter (fun pair => requiredNames.contains pair.1)
      let selectedNames := selected.map (·.1)
      let requiredOnly := required.filter (fun pair => !selectedNames.contains pair.1)
      for (nameString, (_name, info)) in selected ++ requiredOnly do
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
