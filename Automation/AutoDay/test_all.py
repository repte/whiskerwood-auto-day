"""Focused checks against the compiled Auto Day actor, without starting a day."""

import unreal
import toolset_registry
from editor_toolset.toolsets.blueprint import BlueprintTools as BP


ROOT = "/Game/Mods/AutoDay"


def test_poll_clock(actor):
    call = lambda name, *args: actor.call_method(name, args=args)
    assert call("ResetSession")
    for invalid in (-1.0, float("nan"), float("inf"), -float("inf")):
        assert not call("TakePoll", invalid), "Invalid clock must not authorize work"
    assert call("TakePoll", 0.0), "First valid poll should be immediate"
    assert not call("TakePoll", 0.0), "Duplicate frame cannot poll twice"
    assert not call("TakePoll", 0.99), "Native reads must be limited to once per second"
    assert call("TakePoll", 1.0)
    assert not call("TakePoll", 1.99)
    assert call("TakePoll", 2.0)
    assert call("TakePoll", 10.0), "Long frames permit one poll, not a catch-up loop"
    assert not call("TakePoll", 10.0)
    assert not call("TakePoll", 5.0), "Backward clock must reset without authorizing work"
    assert not call("TakePoll", 5.99)
    assert call("TakePoll", 6.0)
    assert call("ResetSession")
    assert call("TakePoll", 0.0), "Load reset must also clear the previous clock"


def test_attempt_guard(actor):
    call = lambda name, *args: actor.call_method(name, args=args)
    assert call("ResetSession")
    for year, day in ((-1, 1), (1, -1), (-1, -1)):
        assert not call("TryMarkAttempt", year, day, True), "Invalid calendar must not consume an attempt"
    assert not call("TryMarkAttempt", 0, 0, False)
    assert call("TryMarkAttempt", 0, 0, True), "Zero-based calendar values are valid"
    assert not call("TryMarkAttempt", 0, 0, True), "Same day must never dispatch twice"
    assert not call("TryMarkAttempt", 0, 1, False), "Not-ready state must leave the next day available"
    assert call("TryMarkAttempt", 0, 1, True)
    assert not call("TryMarkAttempt", 0, 1, True)
    assert call("TryMarkAttempt", 1, 0, True), "Year rollover must create a new day key"
    assert not call("TryMarkAttempt", 1, 0, True)
    assert call("ResetSession")
    assert call("TryMarkAttempt", 1, 0, True), "Loading the same calendar in a new session must reset attempts"
    assert not call("TryMarkAttempt", 1, 0, True)


def test_native_hud_guards(actor, actors):
    native = lambda name: unreal.load_class(None, "/Script/ProjectArco." + name)
    put = lambda obj, key, value: obj.set_editor_property(
        key, value, notify_mode=unreal.PropertyAccessChangeNotifyMode.NEVER)
    # Controllers are not editor-placeable, but may be spawned in the editor world.
    transform = unreal.Transform()
    gameplay = unreal.get_default_object(unreal.GameplayStatics)
    controller = gameplay.call_method("BeginDeferredActorSpawnFromClass", args=(
        actor, native("PlayerController_Play"), transform,
        unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN, None,
        unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))
    controller = gameplay.call_method("FinishSpawningActor", args=(
        controller, transform, unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))
    assert controller, "Native controller fixture must be constructible"
    hud = unreal.new_object(native("PlayHud"))
    assert hud, "Native HUD fixture must be constructible"

    def check(h=hud, p=controller):
        return actor.call_method("HudAllowsConfirmation", args=(h, p))

    def set_player(key, value):
        state = controller.get_editor_property("m_state")
        put(state, key, value)
        put(controller, "m_state", state)

    def set_hud(key, value, nested=None):
        state = hud.get_editor_property("m_hudState")
        # The game exposes these values read-only; import only the fixture field.
        field = f"{key}={'True' if value else 'False'}"
        assert state.import_text(f"({nested}=({field}))" if nested else f"({field})")
        observed = hud.get_editor_property("m_hudState")
        if nested:
            observed = observed.get_editor_property(nested)
        assert observed.get_editor_property(key) == value, "Fixture field must be stored on the native HUD"

    try:
        assert not check(None, controller)
        assert not check(hud, None)
        put(hud, "m_uiHasFadedIn", True)
        set_player("m_showHud", True)
        set_player("m_dev_hideAllHud", False)
        set_player("m_showReplayMenu", False)
        set_player("activeArcoView", None)
        set_hud("eodPending", True)
        set_hud("showSaving", False)
        set_hud("victoryPending", False)
        set_hud("isPausedByEod", True, "TimeHudState")
        set_hud("showHudRoot", True, "sectionVisibilities")
        set_hud("allowEod", True, "sectionVisibilities")
        assert check(), "Current EOD with visible HUD and no open view must be accepted"
        for key, blocked, allowed in (("m_showHud", False, True), ("m_dev_hideAllHud", True, False),
                                      ("m_showReplayMenu", True, False)):
            set_player(key, blocked)
            assert not check(), "Player guard not enforced: " + key
            set_player(key, allowed)
            assert check()
        for key, blocked, allowed, nested in (
                ("eodPending", False, True, None), ("showSaving", True, False, None),
                ("victoryPending", True, False, None),
                ("isPausedByEod", False, True, "TimeHudState"),
                ("showHudRoot", False, True, "sectionVisibilities"),
                ("allowEod", False, True, "sectionVisibilities")):
            set_hud(key, blocked, nested)
            assert not check(), "Native HUD guard not enforced: " + key
            set_hud(key, allowed, nested)
            assert check()
        put(hud, "m_uiHasFadedIn", False)
        assert not check(), "Fading/loading HUD must not start a day"
        put(hud, "m_uiHasFadedIn", True)
        view = unreal.new_object(native("ArcoView"))
        set_player("activeArcoView", view)
        assert not check(), "Native action must not close an unrelated view"
        set_player("activeArcoView", None)
        assert check()
        set_hud("IsPaused", True, "TimeHudState")
        set_hud("IsPaused", True, "replayState")
        assert check(), "User approved regular EOD confirmation despite an additional pause"
        set_hud("isPausedByEod", False, "TimeHudState")
        assert not check(), "A normal daytime pause must never be confirmed"
    finally:
        actors.destroy_actor(controller)


def test_native_wiring():
    bp = unreal.load_asset(ROOT + "/BP_MapLoad")
    pump = BP.read_graph_dsl(BP.get_graph(bp, "Pump"))
    assert pump.count("HandleHudAction") == 1 and '"startNewDay"' in pump
    assert pump.index("HudAllowsConfirmation") < pump.index("TryMarkAttempt") < pump.index("HandleHudAction")
    assert "CurrentInitPhase" in pump and "DONE" in pump and "IsLive" in pump
    assert "ReadModOptionValue" in pump and '"AutoDay.on"' in pump
    for name in ("BP_MapLoad", "BP_MainMenuLoad"):
        asset = unreal.load_asset(ROOT + "/" + name)
        assert asset, "Both loader entry points must exist"
        registration = BP.get_graph(asset, "RegisterOption")
        nodes = [node for node in BP.get_node_infos(BP.find_nodes(registration))
                 if {"optionId", "DefaultValue", "Values"}.issubset({pin.name for pin in node.input_pins})]
        assert len(nodes) == 1, [(node.type_id, [pin.name for pin in node.input_pins])
                                 for node in BP.get_node_infos(BP.find_nodes(registration))]
        default_pin = next(pin for pin in nodes[0].input_pins if pin.name == "DefaultValue")
        assert not default_pin.connected_pins
        assert BP.get_pin_value(default_pin.pin_id).strip('"') == "AutoDay.on"
        for graph in BP.list_graphs(asset):
            source = BP.read_graph_dsl(graph)
            assert "WorkerOptimizer" not in source, "Auto Day must remain independent"
            assert not any(action in source for action in ("forceEod", "skipEod", "Arco_SetDayPhase"))
    events = BP.read_graph_dsl(BP.get_graph(bp, "EventGraph"))
    assert "EventTick" in events and "Pump" in events
    assert "ResetSession" in BP.read_graph_dsl(BP.get_graph(bp, "OnLoaded"))


def run():
    cls = unreal.load_class(None, ROOT + "/BP_MapLoad.BP_MapLoad_C")
    assert cls, "AUTODAY_MISSING_PRODUCTION: standalone BP_MapLoad has not been implemented"
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_class(cls, unreal.Vector(0, 0, -100000))
    assert actor, "Production actor must be instantiable without BeginPlay"
    try:
        test_poll_clock(actor)
        test_attempt_guard(actor)
        test_native_hud_guards(actor, actors)
        test_native_wiring()
        tick = unreal.get_default_object(cls).get_editor_property("primary_actor_tick")
        assert tick.get_editor_property("start_with_tick_enabled"), "Polling must start without external UI"
        assert tick.get_editor_property("tick_even_when_paused"), "EOD pause must not stop the real-time gate"
        unreal.log("AUTODAY_TESTS_PASS: compiled production actor; clock and attempt guards, real native HUD fixtures, default-on independent loader wiring; no native day action invoked")
    finally:
        actors.destroy_actor(actor)


run()
