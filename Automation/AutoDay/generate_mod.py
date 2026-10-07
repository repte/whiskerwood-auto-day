"""Author the two standalone loader Blueprints. Run inside the modkit editor."""
import json
from pathlib import Path

import unreal
import toolset_registry
from editor_toolset.toolsets.blueprint import BlueprintTools as BP, ContainerType
from editor_toolset.toolsets import blueprint_dsl

ROOT = "/Game/Mods/AutoDay"
g = lambda name: f"(Variables|Default|Get{name})"
put = lambda name, value: f"(Variables|Default|Set{name} {value})"
present = lambda value: f"(CallFunction|HasObject :Object {value})"
native = lambda name: unreal.load_class(None, "/Script/ProjectArco." + name)
api_class = unreal.load_class(None, "/Script/SystemCore.ModAPI")


def clear_body(graph):
    kept_result = False
    for node in BP.find_nodes(graph):
        kind = node.get_class().get_name()
        if kind == "K2Node_FunctionEntry":
            continue
        if kind == "K2Node_FunctionResult" and not kept_result:
            kept_result = True
            for pin in BP.get_node_infos([node])[0].input_pins:
                for other in pin.connected_pins:
                    BP.break_pins(other, pin.pin_id)
            continue
        BP.delete_node(node)


def generate(name, gameplay):
    bp = unreal.load_asset(ROOT + "/" + name)
    if bp is None:
        bp = BP.create(ROOT, name, unreal.Actor.static_class())
    variables = {"bool": "Registered", "string[]": "OptionValues"}
    if gameplay:
        variables.update({"bool": "Registered Bound HasClock HasAttempt ShuttingDown",
                          "real": "LastPoll", "int": "AttemptYear AttemptDay"})
    for kind, names in variables.items():
        for var in names.split():
            if var not in BP.list_variables(bp):
                BP.add_variable(bp, var, kind.removesuffix("[]"),
                                container_type=ContainerType.ARRAY if kind.endswith("[]") else None)
    if "API" not in BP.list_variables(bp):
        BP.add_object_variable(bp, "API", api_class)
    if "Translations" not in BP.list_variables(bp):
        map_type = unreal.BlueprintEditorLibrary.get_map_type(
            unreal.BlueprintEditorLibrary.get_basic_type_by_name("name"),
            unreal.BlueprintEditorLibrary.get_basic_type_by_name("string"))
        assert unreal.BlueprintEditorLibrary.add_member_variable(bp, "Translations", map_type)
    definitions = {"HasObject": [("Object", unreal.Object.static_class())], "RegisterOption": []}
    void = set()
    if gameplay:
        definitions.update({
            "TakePoll": [("NowSeconds", "real")],
            "TryMarkAttempt": [("Year", "int"), ("Day", "int"), ("Ready", "bool")],
            "ResetSession": [], "Pump": [], "BeginSession": [], "Shutdown": [],
            "HudAllowsConfirmation": [("InputHud", native("PlayHud")),
                                       ("InputController", native("PlayerController_Play"))],
            "BindLoading": [], "UnbindLoading": [], "OnLoaded": [],
        })
        void = {"BindLoading", "UnbindLoading", "OnLoaded"}
    graphs = {}
    existing = {str(graph.get_name()) for graph in BP.list_graphs(bp)}
    for function, params in definitions.items():
        graphs[function] = BP.get_graph(bp, function) if function in existing else BP.add_function_graph(bp, function)
        if function not in existing:
            for param, kind in params:
                if isinstance(kind, str):
                    BP.add_function_param(graphs[function], param, kind, True)
                else:
                    BP.add_object_function_param(graphs[function], param, kind, True)
            if function not in void:
                BP.add_function_param(graphs[function], "Result", "bool", False)
    BP.compile_blueprint(bp)

    code = {}
    code["HasObject"] = '(fn HasObject (Object) (Utilities|IsValid Object (:"Is Valid" (return true)) (:"Is Not Valid" (return false))))'
    strings = {
        "title": ("Auto Day: automatically start the next day", "Auto Day: naechsten Tag automatisch starten"),
        "description": ("Confirms the regular end of day when no window is open. On by default.",
                        "Bestaetigt das regulaere Tagesende, wenn kein Fenster offen ist. Standard: an."),
        "off": ("Off", "Aus"), "on": ("On", "An"),
    }
    translation_lines = []
    for key, (en, de) in strings.items():
        translation_lines.append(f'(Utilities|Map|Add {g("Translations")} "AutoDay.{key}" (select (== language "de") {json.dumps(de)} {json.dumps(en)}))')
    code["RegisterOption"] = f'''(fn RegisterOption ()
        (if {g('Registered')} (return true))
        (bind api (Class|ModAPI|GetModAPI))
        (if (not {present('api')}) (return false))
        {put('API', 'api')}
        (bind languages (Class|ModAPI|ListLanguageIds :self api))
        (for language languages
          (Utilities|Map|Clear {g('Translations')})
          {' '.join(translation_lines)}
          (Class|ModAPI|AddNewStrings :self api :langId language :idStringPairs {g('Translations')}))
        (Utilities|Array|Clear {g('OptionValues')})
        (Utilities|Array|Add {g('OptionValues')} "AutoDay.off")
        (Utilities|Array|Add {g('OptionValues')} "AutoDay.on")
        (bind ok (Class|ModAPI|RegisterModOptions :self api :optionId "AutoDay.Enabled"
          :optionDisplayName "AutoDay.title" :Values {g('OptionValues')}
          :DefaultValue "AutoDay.on" :optionDescription "AutoDay.description"))
        {put('Registered', 'ok')} (return ok))'''
    if gameplay:
        def unpack(struct, value, prefix):
            node = "Utilities|Struct|Break" + struct
            pins = BP.get_node_type_pins(graphs["HudAllowsConfirmation"], node).output_pins
            return f"(bind ({' '.join(prefix + str(pin.name) for pin in pins)}) ({node} {value}))"

        code["TakePoll"] = f'''(fn TakePoll (NowSeconds)
            (if (not (and (>= NowSeconds 0.0) (<= NowSeconds 1000000000000.0))) (return false))
            (if (and {g('HasClock')} (< NowSeconds {g('LastPoll')}))
              {put('LastPoll', 'NowSeconds')} (return false))
            (if (and {g('HasClock')} (< (- NowSeconds {g('LastPoll')}) 1.0)) (return false))
            {put('HasClock', 'true')} {put('LastPoll', 'NowSeconds')} (return true))'''
        code["TryMarkAttempt"] = f'''(fn TryMarkAttempt (Year Day Ready)
            (if (or (not Ready) (or (< Year 0) (< Day 0))) (return false))
            (if (and {g('HasAttempt')} (and (== Year {g('AttemptYear')}) (== Day {g('AttemptDay')}))) (return false))
            {put('HasAttempt', 'true')} {put('AttemptYear', 'Year')} {put('AttemptDay', 'Day')} (return true))'''
        code["ResetSession"] = f'''(fn ResetSession ()
            {put('HasAttempt', 'false')} {put('HasClock', 'false')}
            {put('AttemptYear', '-1')} {put('AttemptDay', '-1')} {put('LastPoll', '0.0')} (return true))'''
        code["HudAllowsConfirmation"] = f'''(fn HudAllowsConfirmation (InputHud InputController)
            (if (or (not {present('InputHud')}) (not {present('InputController')})) (return false))
            (if (not (Class|PlayHud|GetMUiHasFadedIn :self InputHud)) (return false))
            {unpack('ArcoPlayerState', '(Class|PlayerControllerPlay|GetMState :self InputController)', 'p_')}
            (if (or {present('p_activeArcoView')} (or (not p_m_showHud) (or p_m_dev_hideAllHud p_m_showReplayMenu))) (return false))
            {unpack('HudState', '(Class|PlayHud|GetMHudState :self InputHud)', 'h_')}
            (if (or (not h_eodPending) (or h_showSaving h_victoryPending)) (return false))
            {unpack('TimeHudState', 'h_TimeHudState', 't_')}
            {unpack('VisibilityToggles', 'h_sectionVisibilities', 'v_')}
            (return (and t_isPausedByEod (and v_showHudRoot v_allowEod))))'''
        code["BindLoading"] = f'(fn BindLoading () (EventDispatchers|BindEventtoOnLoadingFinished :self {g("API")}))'
        code["UnbindLoading"] = f'(fn UnbindLoading () (EventDispatchers|UnbindEventfromOnLoadingFinished :self {g("API")}))'
        code["OnLoaded"] = f'(fn OnLoaded () (if (not {g("ShuttingDown")}) (CallFunction|ResetSession)))'
        code["BeginSession"] = f'''(fn BeginSession ()
            (if {g('ShuttingDown')} (return false))
            (bind registered (CallFunction|RegisterOption)) (if (not registered) (return false))
            (if (not {g('Bound')}) (CallFunction|BindLoading) {put('Bound', 'true')}) (return true))'''
        code["Shutdown"] = f'''(fn Shutdown ()
            {put('ShuttingDown', 'true')}
            (if (and {g('Bound')} {present(g('API'))}) (CallFunction|UnbindLoading))
            {put('Bound', 'false')} (CallFunction|ResetSession) (return true))'''
        code["Pump"] = f'''(fn Pump ()
            (if {g('ShuttingDown')} (return false))
            (bind due (CallFunction|TakePoll :NowSeconds (Utilities|Time|GetRealTimeSeconds)))
            (if (not due) (return false))
            (bind started (CallFunction|BeginSession)) (if (not started) (return false))
            (bind option (Class|ModAPI|ReadModOptionValue :self {g('API')} :optionId "AutoDay.Enabled" :fallbackValue "AutoDay.on"))
            (if (not (Utilities|String|EqualExactly(String) option "AutoDay.on")) (return false))
            (bind mode (Utilities|Casting|CastToProjectArcoGameModeBase :Object (Game|GetGameMode))
              (:then
            (bind phase (Class|ProjectArcoGameModeBase|CurrentInitPhase :self mode))
            (if (not (Utilities|Enum|Equal(Enum) :A phase)) (return false))
            (bind (found systems) (Class|ArcoSystems|GetArcoSys))
            (if (or (not found) (not {present('systems')})) (return false))
            (if (not (Class|ArcoSystems|IsLive :self systems)) (return false))
            (bind player (Utilities|Casting|CastToPlayerController_Play :Object (Game|GetPlayerController :PlayerIndex 0))
              (:then
            (bind hud (Class|PlayerControllerPlay|GetMPlayHud :self player))
            (bind ready (CallFunction|HudAllowsConfirmation :InputHud hud :InputController player))
            (if (not ready) (return false))
            (bind clock (Class|ArcoSystems|GetMWorldTime :self systems))
            (if (not {present('clock')}) (return false))
            (bind accepted (CallFunction|TryMarkAttempt :Year (Class|WorldTime|GetMYear :self clock)
              :Day (Class|WorldTime|GetMDay :self clock) :Ready ready))
            (if (not accepted) (return false))
            (Class|PlayerControllerPlay|HandleHudAction :self player :HudAction (Utilities|Struct|MakeHudAction :action "startNewDay"))
            (Class|ModAPI|LogMessage :self {g('API')} :Msg "AutoDay: requested regular next day." :doPrependDate true)
            (return true))
              (:CastFailed (return false))))
              (:CastFailed (return false))))'''

    for function, source in code.items():
        blueprint_dsl.parse(source)
        graph = graphs[function]
        clear_body(graph)
        if function in ("BindLoading", "UnbindLoading"):
            blueprint_dsl.Transpiler(graph, BP.create_node, BP.connect_pins, BP._get_node_info,
                BP.set_pin_value, lambda current: BP.find_nodes(current), delete_node_fn=BP.delete_node,
                find_node_types_fn=lambda f: BP.find_node_types(graph, f)).transpile(source)
            target = next(node for node in BP.get_node_infos(BP.find_nodes(graph)) if any(pin.name == "Delegate" for pin in node.input_pins))
            event = BP.create_node(graph, "EventDispatchers|CreateEvent", unreal.IntPoint(0, 200))
            info = BP.get_node_infos([event])[0]
            BP.connect_pins(next(pin.pin_id for pin in info.output_pins if pin.name == "OutputDelegate"),
                            next(pin.pin_id for pin in target.input_pins if pin.name == "Delegate"))
            BP.set_create_event_function(event, "OnLoaded")
        else:
            unreal.log("AUTODAY_WRITE " + name + "." + function)
            BP.write_graph_dsl(graph, source)
            if function == "Pump":
                comparisons = [n for n in BP.get_node_infos(BP.find_nodes(graph)) if n.type_id == "Utilities|Enum|Equal(Enum)"]
                assert len(comparisons) == 1
                BP.set_pin_value(next(p.pin_id for p in comparisons[0].input_pins if p.name == "B"), "DONE")
    events = '''(event EventBeginPlay () (CallFunction|BeginSession))
        (event EventTick (DeltaSeconds) (CallFunction|Pump))
        (event EventEndPlay (EndPlayReason) (CallFunction|Shutdown))''' if gameplay else '(event EventBeginPlay () (CallFunction|RegisterOption))'
    BP.write_graph_dsl(BP.get_graph(bp, "EventGraph"), events)
    BP.compile_blueprint(bp, warnings_as_errors=True)
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("hidden", True)
    tick = cdo.get_editor_property("primary_actor_tick")
    tick.set_editor_property("start_with_tick_enabled", gameplay)
    tick.set_editor_property("tick_even_when_paused", gameplay)
    tick.set_editor_property("tick_interval", 0.0)
    cdo.set_editor_property("primary_actor_tick", tick, notify_mode=unreal.PropertyAccessChangeNotifyMode.NEVER)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)
    return code


with toolset_registry.tool_raising_exceptions():
    generate("BP_MainMenuLoad", False)
    code = generate("BP_MapLoad", True)
    Path(unreal.Paths.project_saved_dir(), "AutoDay-Runtime.dsl").write_text("\n\n".join(code.values()), encoding="utf-8")
unreal.log("AUTODAY_GENERATED_PASS")
