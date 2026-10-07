"""Prepare and validate AutoDay's isolated, editor-only cook label."""

import json
from pathlib import Path

import unreal


BASE = "/Game/Mods/AutoDay"
LABEL_NAME = "PAL_AutoDay"
LABEL_PATH = f"{BASE}/{LABEL_NAME}"
RUNTIME_NAMES = ("BP_MapLoad", "BP_MainMenuLoad")
RUNTIME_PATHS = {f"{BASE}/{name}" for name in RUNTIME_NAMES}
NATIVE_PACKAGES = {
    "/Script/CoreUObject", "/Script/Engine", "/Script/InputCore",
    "/Script/ProjectArco", "/Script/SystemCore",
}
ROOT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = ROOT / "Content" / "Mods" / "AutoDay"

descriptor = json.loads((SOURCE / "AutoDay.uplugin").read_text(encoding="utf-8-sig"))
assert descriptor["Name"] == "AutoDay", "Unexpected mod descriptor name"
assert descriptor["Version"] == "0.1.0", "Unexpected mod version"
assert descriptor["EngineVersion"] == "5.8", "Unexpected engine version"
assert descriptor["Description"] and descriptor["CreatedBy"], "Incomplete mod descriptor"
assert not descriptor.get("Modules"), "AutoDay must not require a native DLL"
assert not descriptor.get("Plugins"), "AutoDay must not require another plugin"

allowed_files = {f"{name}.uasset" for name in RUNTIME_NAMES}
allowed_files.update({f"{LABEL_NAME}.uasset", "AutoDay.uplugin"})
for path in SOURCE.rglob("*"):
    if path.is_file():
        assert path.relative_to(SOURCE).as_posix() in allowed_files, f"Unexpected mod source file: {path}"
for asset_path in RUNTIME_PATHS:
    assert unreal.EditorAssetLibrary.does_asset_exist(asset_path), f"Missing runtime entry: {asset_path}"
    assert isinstance(unreal.load_asset(asset_path), unreal.Blueprint), f"Entry is not a Blueprint: {asset_path}"

registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.scan_paths_synchronous(["/Game/Mods"], force_rescan=True)
registry.wait_for_completion()
labels = registry.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "PrimaryAssetLabel"))
used_chunks = {
    data.get_asset().get_editor_property("rules").get_editor_property("chunk_id")
    for data in labels if str(data.package_name) != LABEL_PATH
}
if unreal.EditorAssetLibrary.does_asset_exist(LABEL_PATH):
    label = unreal.load_asset(LABEL_PATH)
    assert isinstance(label, unreal.PrimaryAssetLabel), "Existing cook label has the wrong class"
    chunk = label.get_editor_property("rules").get_editor_property("chunk_id")
    assert 1 <= chunk <= 300 and chunk not in used_chunks, "AutoDay chunk conflicts with another label"
else:
    chunk = next((value for value in range(1, 301) if value not in used_chunks), None)
    assert chunk is not None, "No unused mod chunk available"
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.PrimaryAssetLabel)
    label = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        LABEL_NAME, BASE, unreal.PrimaryAssetLabel, factory,
    )
    assert label, "Could not create AutoDay's cook label"

rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", chunk)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
label.set_editor_property("is_runtime_label", False)
label.set_editor_property("explicit_assets", [])
label.set_editor_property("explicit_blueprints", [])
assert unreal.EditorAssetLibrary.save_loaded_asset(label), "Could not save AutoDay's cook label"

registry.scan_paths_synchronous([BASE], force_rescan=True)
registry.wait_for_completion()
assets = registry.get_assets_by_path(BASE, recursive=True, include_only_on_disk_assets=True)
assert {str(data.package_name) for data in assets} == RUNTIME_PATHS | {LABEL_PATH}, "Unexpected AutoDay asset inventory"
options = unreal.AssetRegistryDependencyOptions(
    include_soft_package_references=True, include_hard_package_references=True,
    include_searchable_names=False, include_soft_management_references=False,
    include_hard_management_references=False,
)
assert registry.get_dependencies(BASE + "/__MissingDependencyBoundary", options) is None, "Dependency lookup must distinguish missing assets"
for asset_path in sorted(RUNTIME_PATHS):
    dependencies = registry.get_dependencies(asset_path, options)
    assert dependencies is not None, f"Missing dependency information: {asset_path}"
    for dependency in dependencies:
        path = str(dependency)
        # Standard Blueprint macros are expanded during compilation.
        if path == "/Engine/EditorBlueprintResources/StandardMacros":
            continue
        assert path in RUNTIME_PATHS or path in NATIVE_PACKAGES, (
            "Unexpected runtime dependency", asset_path, path,
        )

saved = Path(unreal.Paths.project_saved_dir()).resolve()
saved.mkdir(parents=True, exist_ok=True)
(saved / "AutoDay-PackageSetup.json").write_text(
    json.dumps({"mod": "AutoDay", "version": "0.1.0", "chunk": chunk,
                "runtime_assets": list(RUNTIME_NAMES)}, indent=2) + "\n",
    encoding="utf-8",
)
unreal.log(f"AUTODAY_PACKAGE_SETUP_PASS: isolated chunk={chunk}, native entries, editor-only label")
