export const EN = {
  header: "Cover Time Based Configuration",
  loading: "Loading...",
  saving: "Saving...",
  save_failed: "Save failed — value reverted",
  confirm_cancel_calibration: "A calibration is running. Cancel it and continue?",
  create_new: "+ Create new cover entity",
  yaml_warning:
    "This entity uses YAML configuration and cannot be configured from this card. Please migrate to the UI: Settings \u2192 Devices & Services \u2192 Helpers \u2192 Create Helper \u2192 Cover Time Based.",
  load_failed: "Failed to load configuration. Please try again.",
  admin_required:
    "This card needs an administrator account. Sign in as an administrator to configure covers.",
  "tabs.device": "Device",
  "tabs.calibration": "Calibration",
  "control_mode.label": "Control Mode",
  "control_mode.wrapped": "Wrap an existing cover entity",
  "control_mode.switch": "Switch (latching)",
  "control_mode.pulse": "Pulse (momentary)",
  "control_mode.toggle": "Toggle (same button)",
  "control_mode.toggle_opposite": "Toggle (opposite button)",
  "control_mode.single_button": "Single button (cycling)",
  "control_mode.pulse_time": "Pulse time",
  "entities.cover_entity": "Cover Entity",
  "position_reporting.label": "Position reporting",
  "position_reporting.reliable": "Reliable position feedback",
  "position_reporting.reliable_helper":
    "The wrapped cover reports a trustworthy position and reaches its real open/closed endpoints. The default — the right choice unless the tracked position drifts from where the cover actually is.",
  "position_reporting.unreliable": "Position unreliable — track by time",
  "position_reporting.unreliable_helper":
    "Track position by time only and ignore the position the wrapped cover reports. Enable this if the underlying cover reports an unreliable position.",
  "position_reporting.no_endpoints": "No real endpoints — reports open/closed when stopped",
  "position_reporting.no_endpoints_helper":
    "For covers with no position feedback that report open/closed when the motor stops mid-travel rather than only at the physical endpoints. A reported closed state stops tracking at the calculated position instead of snapping to 0%.",
  "position_reporting.command_echo": "State mirrors the last command",
  "position_reporting.command_echo_helper":
    "Enable for covers (e.g. some Tuya shutters) whose open/closed/unknown state is a command echo rather than a real endpoint — they report no opening/closing transition and no position. The state is treated as an open/close/stop command and the position is tracked by time.",
  "position_reporting.ignore_all": "Ignore all device reports",
  "position_reporting.ignore_all_helper":
    "The device's state and position are all untrustworthy. Ignore everything it reports and track the position purely from the open/close timers. Home Assistant becomes the only way to move the cover — operating it by a wall switch or remote is not tracked.",
  "position_reporting.docs_link": "Learn more",
  "entities.force_time_based_position": "Force time-based positioning",
  "entities.force_time_based_position_helper":
    "By default, if the wrapped cover supports setting a position, the set-position command is sent straight to it. Enable this to instead drive it with timed open/close/stop, ignoring its native set-position support.",
  "entities.invert": "Invert position",
  "entities.invert_helper":
    "Flip the position axis: report 100 − the wrapped cover's position, and swap open/close. Use for covers that run backwards, e.g. an awning where the underlying entity reports open = extended. Position axis only; the tilt logic is unchanged — intended for position-only covers (awnings/shutters), not tilting venetians.",
  "entities.switch_entities": "Switch Entities",
  "entities.open_switch": "Open switch",
  "entities.close_switch": "Close switch",
  "entities.stop_switch": "Stop switch",
  "entities.switch_entities_pulse": "Switch / Script Entities",
  "entities.open_switch_pulse": "Open switch or script",
  "entities.close_switch_pulse": "Close switch or script",
  "entities.stop_switch_pulse": "Stop switch or script",
  "entities.button": "Button",
  "tilt.label": "Tilt Mode",
  "tilt.none": "Not supported",
  "tilt.sequential_close": "Closes then tilts closed",
  "tilt.sequential_open": "Closes then tilts open",
  "tilt.dual_motor": "Separate tilt motor",
  "tilt.inline": "Tilts inline with travel",
  "tilt_motor.label": "Tilt Motor",
  "tilt_motor.open_switch": "Tilt open switch",
  "tilt_motor.close_switch": "Tilt close switch",
  "tilt_motor.stop_switch": "Tilt stop switch",
  "tilt_motor.label_pulse": "Tilt Motor (switch or script)",
  "tilt_motor.open_switch_pulse": "Tilt open switch or script",
  "tilt_motor.close_switch_pulse": "Tilt close switch or script",
  "tilt_motor.stop_switch_pulse": "Tilt stop switch or script",
  "tilt_motor.safe_position": "Safe tilt position",
  "tilt_motor.safe_position_helper": "Tilt moves here before travel (100 = fully open)",
  "tilt_motor.max_allowed_position": "Max tilt allowed position (optional)",
  "tilt_motor.max_allowed_helper":
    "Tilt only allowed when cover position is at or below this value (0 = closed, 100 = open)",
  "tilt.close_includes_tilt": "Close cover also closes slats",
  "tilt.close_includes_tilt_helper": "When closing, slats tilt closed at the end of travel",
  "assumed_state.label": "Assumed state",
  "assumed_state.helper":
    "When on, Home Assistant treats the position as estimated and keeps both open and close controls active. Turn off if you trust the time-based calculation and want the UI to grey out unavailable actions (e.g. close when already closed).",
  "relay_reports_off.label": "Relay reports its own OFF",
  "relay_reports_off.helper":
    "Leave on for normal toggle relays, which switch themselves off after the pulse and report it. Turn off for hardware-managed pulse modules (e.g. Aqara T2) that pulse internally but never report when they switch off, leaving the switch entity stuck on. With it off, the integration only ever sends a single ON command per press and never an OFF — so each press is exactly one clean activation, with no doubled commands.",
  "send_endpoint_stop.label": "Send stop signal at endpoints",
  "send_endpoint_stop.helper":
    "When your cover reaches fully open or closed, send the stop pulse. Keep this on for controllers that keep running until they receive a stop (the cover otherwise gets stuck and physical buttons stop responding). Turn it off if your motor stops itself at its limits and an extra stop makes it move to a preset/favourite position.",
  "force_endpoint_redrive.label": "Always re-send open/close at the endpoints",
  "force_endpoint_redrive.helper":
    "For covers with no position feedback that can also be moved by an external remote, so Home Assistant may wrongly believe they are already fully open or closed. When on, an open or close command is always driven for the full travel time even if Home Assistant thinks the cover is already there — guaranteeing the command reaches the motor. Leave off for covers that report their own position.",
  "wait_for_relay_feedback.label": "Wait for relay confirmation before tracking",
  "wait_for_relay_feedback.helper":
    "Starts the position timer when the relay reports it switched on, instead of the moment the command is sent. On a slow or cold Zigbee/Z-Wave mesh the command can take seconds to reach the relay; without this, that delay is counted as travel and the tracked position runs ahead of the cover. Leave off unless the position drifts on covers whose relay responds slowly.",
  "recalibrate_before_position.label": "Fully open before moving to a position (Beta)",
  "recalibrate_before_position.helper":
    "For covers with no position feedback that a remote can also move. Drives the cover fully open before each position command, so the move starts from a known position instead of a drifted guess. Roughly doubles the travel of every move, and on inline or sequential tilt it moves the cover when you adjust the slats.",
  "resync.label": "Resync",
  "resync.helper":
    "Tell the integration the cover's true position after it was moved by the physical button or an RF remote. This re-anchors tracking and stops the motor if Home Assistant is still driving it; it never starts one.",
  more_info: "More info",
  "timing.travel_attribute_header": "Travel Attribute",
  "timing.tilt_attribute_header": "Tilt Attribute",
  "timing.value_header": "Value",
  "timing.not_set": "Not set",
  "timing.travel_time_close": "Travel time (close)",
  "timing.travel_time_open": "Travel time (open)",
  "timing.travel_startup_delay": "Travel startup delay",
  "timing.tilt_time_close": "Tilt time (close)",
  "timing.tilt_time_open": "Tilt time (open)",
  "timing.tilt_startup_delay": "Tilt startup delay",
  "timing.min_movement_time": "Minimum movement time",
  "timing.endpoint_runon_time": "Endpoint run-on time",
  "position.label": "Current Position",
  "position.helper": "Move cover to a known endpoint, then set position.",
  "position.unknown": "Unknown",
  "position.open": "Fully open",
  "position.closed": "Fully closed",
  "position.closed_tilt_open": "Fully closed, tilt open",
  "position.closed_tilt_closed": "Fully closed, tilt closed",
  "calibration.label": "Timing Calibration",
  "calibration.attribute_label": "Attribute",
  "calibration.start": "Start",
  "calibration.active": "Calibration Active",
  "calibration.step": "Step {step}",
  "calibration.final_step": "Final step",
  "calibration.cancel": "Cancel",
  "calibration.finish": "Finish",
  "calibration.set_position_first": "Set position to start calibration.",
  "controls.cover_label": "Cover",
  "controls.tilt_label": "Tilt",
  "controls.open": "Open",
  "controls.stop": "Stop",
  "controls.close": "Close",
  "controls.tilt_open": "Tilt open",
  "controls.tilt_stop": "Tilt stop",
  "controls.tilt_close": "Tilt close",
  "hints.sequential_close.travel_time_close":
    "Start with cover fully open. Click Finish when the cover is fully closed, before the slats start tilting.",
  "hints.sequential_close.travel_time_open":
    "Start with cover closed and slats open. Click Finish when the cover is fully open.",
  "hints.sequential_close.tilt_time_close":
    "Start with cover closed but slats open. Click Finish when the slats are fully closed.",
  "hints.sequential_close.tilt_time_open":
    "Start with cover and slats closed. Click Finish when the slats are open.",
  "hints.sequential_open.travel_time_close":
    "Start with cover fully open and slats closed. Click Finish when the cover is fully closed, before the slats start tilting open.",
  "hints.sequential_open.travel_time_open":
    "Start with cover closed and slats closed. Click Finish when the cover is fully open.",
  "hints.sequential_open.tilt_time_close":
    "Start with cover closed but slats open. Click Finish when the slats are fully closed.",
  "hints.sequential_open.tilt_time_open":
    "Start with cover and slats closed. Click Finish when the slats are fully open.",
  "hints.dual_motor.travel_time_close":
    "Start with cover open and slats in safe position. Click Finish when the cover is fully closed.",
  "hints.dual_motor.travel_time_open":
    "Start with cover closed and slats in safe position. Click Finish when the cover is fully open.",
  "hints.dual_motor.tilt_time_close":
    "Start with cover closed and slats open. Click Finish when the slats are fully closed.",
  "hints.dual_motor.tilt_time_open":
    "Start with both cover and slats closed. Click Finish when the slats are fully open.",
  "hints.inline.travel_time_close":
    "Start with both cover and slats fully open. Click Finish when both are fully closed.",
  "hints.inline.travel_time_open":
    "Start with both cover and slats fully closed. Click Finish when both are fully open.",
  "hints.inline.tilt_time_close":
    "Start with slats fully open. Click Finish when the slats are fully closed.",
  "hints.inline.tilt_time_open":
    "Start with slats fully closed. Click Finish when the slats are fully open.",
  "hints.none.travel_time_close": "Click Finish when the cover is fully closed.",
  "hints.none.travel_time_open": "Click Finish when the cover is fully open.",
  "hints.min_movement_time": "Click Finish as soon as you notice the cover moving.",
};

export const TRANSLATIONS = {
  en: EN,
  pt: {
    header: "Configuração de Estore Baseado em Tempo",
    loading: "A carregar...",
    saving: "A guardar...",
    save_failed: "Falha ao guardar — valor revertido",
    confirm_cancel_calibration: "Existe uma calibração em curso. Cancelar e continuar?",
    create_new: "+ Criar nova entidade de estore",
    yaml_warning:
      "Esta entidade utiliza configuração YAML e não pode ser configurada a partir deste cartão. Por favor, migre para a interface gráfica: Definições > Dispositivos e Serviços > Auxiliares > Criar Auxiliar > Estore Baseado em Tempo.",
    load_failed: "Falha ao carregar a configuração. Por favor, tente novamente.",
    admin_required:
      "Este cartão requer uma conta de administrador. Inicie sessão como administrador para configurar estores.",
    "tabs.device": "Dispositivo",
    "tabs.calibration": "Calibração",
    "control_mode.label": "Modo de Controlo",
    "control_mode.wrapped": "Encapsular uma entidade de estore existente",
    "control_mode.switch": "Interruptor (travamento)",
    "control_mode.pulse": "Pulso (momentâneo)",
    "control_mode.toggle": "Alternar (mesmo botão)",
    "control_mode.toggle_opposite": "Alternar (botão oposto)",
    "control_mode.single_button": "Botão único (cíclico)",
    "control_mode.pulse_time": "Duração do pulso",
    "entities.cover_entity": "Entidade de Estore",
    "position_reporting.label": "Reporte de posição",
    "position_reporting.reliable": "Retorno de posição fiável",
    "position_reporting.reliable_helper":
      "O estore envolvido reporta uma posição fiável e alcança os seus extremos reais de aberto/fechado. A predefinição — a escolha certa a menos que a posição rastreada se desvie de onde o estore realmente está.",
    "position_reporting.unreliable": "Posição não fiável — rastrear pelo tempo",
    "position_reporting.unreliable_helper":
      "Rastrear a posição apenas pelo tempo e ignorar a posição reportada pelo estore. Ative isto se o estore subjacente reportar uma posição não fiável.",
    "position_reporting.no_endpoints": "Sem extremos reais — reporta aberto/fechado quando parado",
    "position_reporting.no_endpoints_helper":
      "Para estores sem retorno de posição que reportam aberto/fechado quando o motor para a meio do deslocamento, em vez de apenas nos extremos físicos. Um estado fechado reportado interrompe o rastreio na posição calculada, em vez de saltar para 0%.",
    "position_reporting.command_echo": "O estado espelha o último comando",
    "position_reporting.command_echo_helper":
      "Ative para estores (por exemplo, alguns estores Tuya) cujo estado aberto/fechado/desconhecido é um eco do comando em vez de uma posição final real — não reportam transição de abertura/fecho nem posição. O estado é tratado como um comando abrir/fechar/parar e a posição é rastreada pelo tempo.",
    "position_reporting.ignore_all": "Ignorar todos os relatórios do dispositivo",
    "position_reporting.ignore_all_helper":
      "O estado e a posição do dispositivo não são fiáveis. Ignore tudo o que ele reporta e rastreie a posição apenas pelos temporizadores de abertura/fecho. O Home Assistant passa a ser a única forma de mover o estore — operá-lo por um interruptor de parede ou comando não é rastreado.",
    "position_reporting.docs_link": "Saber mais",
    "entities.force_time_based_position": "Forçar posicionamento por tempo",
    "entities.force_time_based_position_helper":
      "Por predefinição, se o estore envolvido suportar definir a posição, o comando de definir posição é enviado diretamente para ele. Ative isto para o controlar com abrir/fechar/parar temporizados, ignorando o suporte nativo de definir posição.",
    "entities.invert": "Inverter posição",
    "entities.invert_helper":
      "Inverte o eixo da posição: reporta 100 − a posição do estore envolvido e troca abrir/fechar. Use para estores que funcionam ao contrário, por exemplo um toldo cuja entidade subjacente reporta aberto = estendido. Apenas o eixo da posição; a lógica de inclinação não é alterada — destinado a estores apenas de posição (toldos/estores), não a venezianas de lâminas orientáveis.",
    "entities.switch_entities": "Entidades de Interruptor",
    "entities.open_switch": "Interruptor de abrir",
    "entities.close_switch": "Interruptor de fechar",
    "entities.stop_switch": "Interruptor de parar",
    "entities.switch_entities_pulse": "Entidades de Interruptor / Script",
    "entities.open_switch_pulse": "Interruptor ou script de abrir",
    "entities.close_switch_pulse": "Interruptor ou script de fechar",
    "entities.stop_switch_pulse": "Interruptor ou script de parar",
    "entities.button": "Botão",
    "tilt.label": "Inclinação",
    "tilt.none": "Não suportado",
    "tilt.sequential_close": "Fecha e depois inclina fechadas",
    "tilt.sequential_open": "Fecha e depois inclina abertas",
    "tilt.dual_motor": "Motor de inclinação separado",
    "tilt.inline": "Inclina durante o deslocamento",
    "tilt_motor.label": "Motor de Inclinação",
    "tilt_motor.open_switch": "Interruptor de abrir inclinação",
    "tilt_motor.close_switch": "Interruptor de fechar inclinação",
    "tilt_motor.stop_switch": "Interruptor de parar inclinação",
    "tilt_motor.label_pulse": "Motor de Inclinação (interruptor ou script)",
    "tilt_motor.open_switch_pulse": "Interruptor ou script de abrir inclinação",
    "tilt_motor.close_switch_pulse": "Interruptor ou script de fechar inclinação",
    "tilt_motor.stop_switch_pulse": "Interruptor ou script de parar inclinação",
    "tilt_motor.safe_position": "Posição de inclinação segura",
    "tilt_motor.safe_position_helper":
      "A inclinação move-se para aqui antes do deslocamento (100 = totalmente aberto)",
    "tilt_motor.max_allowed_position": "Posição máxima permitida de inclinação (opcional)",
    "tilt_motor.max_allowed_helper":
      "A inclinação só é permitida quando a posição do estore está neste valor ou abaixo (0 = fechado, 100 = aberto)",
    "tilt.close_includes_tilt": "Fechar estore também fecha lâminas",
    "tilt.close_includes_tilt_helper":
      "Ao fechar, as lâminas inclinam para fechado no fim do percurso",
    "assumed_state.label": "Estado assumido",
    "assumed_state.helper":
      "Quando ativo, o Home Assistant trata a posição como estimada e mantém ativos os controlos de abrir e fechar. Desative se confiar no cálculo por tempo e quiser que a interface desative as ações indisponíveis (por exemplo, fechar quando já está fechado).",
    "relay_reports_off.label": "O relé reporta o seu próprio OFF",
    "relay_reports_off.helper":
      "Deixe ativo para relés de alternância normais, que se desligam após o pulso e o reportam. Desative para módulos de pulso geridos por hardware (por exemplo, Aqara T2) que pulsam internamente mas nunca reportam quando se desligam, deixando a entidade de interruptor presa em ligado. Com a opção desativada, a integração envia apenas um único comando LIGAR por toque e nunca DESLIGAR — por isso cada toque é exatamente uma ativação limpa, sem comandos duplicados.",
    "send_endpoint_stop.label": "Enviar sinal de paragem nos extremos",
    "send_endpoint_stop.helper":
      "Quando a cobertura chega totalmente aberta ou fechada, envia o pulso de paragem. Mantenha ativo para controladores que continuam a funcionar até receberem uma paragem (caso contrário a cobertura fica presa e os botões físicos deixam de responder). Desative se o seu motor para sozinho nos limites e um pulso de paragem adicional o faz mover para uma posição predefinida/favorita.",
    "force_endpoint_redrive.label": "Reenviar sempre abrir/fechar nos extremos",
    "force_endpoint_redrive.helper":
      "Para estores sem retorno de posição que também podem ser movidos por um telecomando externo, pelo que o Home Assistant pode julgar erradamente que já estão totalmente abertos ou fechados. Quando ativo, um comando de abrir ou fechar é sempre executado durante o tempo total de deslocamento, mesmo que o Home Assistant pense que o estore já lá está — garantindo que o comando chega ao motor. Deixe inativo para estores que reportam a sua própria posição.",
    "wait_for_relay_feedback.label": "Aguardar confirmação do relé antes de rastrear",
    "wait_for_relay_feedback.helper":
      "Inicia o temporizador de posição quando o relé reporta que ligou, em vez do momento em que o comando é enviado. Numa malha Zigbee/Z-Wave lenta ou fria, o comando pode demorar segundos a chegar ao relé; sem esta opção, esse atraso é contado como deslocamento e a posição rastreada fica à frente do estore. Deixe inativo, a menos que a posição desvie em estores cujo relé responde lentamente.",
    "recalibrate_before_position.label": "Abrir totalmente antes de mover para uma posição (Beta)",
    "recalibrate_before_position.helper":
      "Para estores sem retorno de posição que também podem ser movidos por um telecomando. Antes de cada comando de definir posição, move primeiro o estore para totalmente aberto, para que o movimento comece a partir de uma posição conhecida em vez de uma estimativa desviada. Isto duplica, grosso modo, o tempo de deslocamento de cada movimento e, na inclinação durante o deslocamento ou na inclinação sequencial, ajustar as lâminas também move o estore.",
    "resync.label": "Ressincronizar",
    "resync.helper":
      "Indica à integração a posição real do estore depois de ter sido movido pelo botão físico ou por um telecomando RF. Isto reancora o rastreio da posição e para o motor se o Home Assistant ainda o estiver a acionar; nunca o põe em movimento.",
    more_info: "Mais informação",
    "timing.travel_attribute_header": "Atributo de deslocamento",
    "timing.tilt_attribute_header": "Atributo de inclinação",
    "timing.value_header": "Valor",
    "timing.not_set": "Não definido",
    "timing.travel_time_close": "Tempo de deslocamento (fechar)",
    "timing.travel_time_open": "Tempo de deslocamento (abrir)",
    "timing.travel_startup_delay": "Atraso de arranque do deslocamento",
    "timing.tilt_time_close": "Tempo de inclinação (fechar)",
    "timing.tilt_time_open": "Tempo de inclinação (abrir)",
    "timing.tilt_startup_delay": "Atraso de arranque da inclinação",
    "timing.min_movement_time": "Tempo mínimo de movimento",
    "timing.endpoint_runon_time": "Tempo de sobrecurso nos extremos",
    "position.label": "Posição Atual",
    "position.helper": "Mova o estore para um extremo conhecido e defina a posição.",
    "position.unknown": "Desconhecida",
    "position.open": "Totalmente aberto",
    "position.closed": "Totalmente fechado",
    "position.closed_tilt_open": "Totalmente fechado, inclinação aberta",
    "position.closed_tilt_closed": "Totalmente fechado, inclinação fechada",
    "calibration.label": "Calibração de Temporização",
    "calibration.attribute_label": "Atributo",
    "calibration.start": "Iniciar",
    "calibration.active": "Calibração Ativa",
    "calibration.step": "Passo {step}",
    "calibration.final_step": "Passo final",
    "calibration.cancel": "Cancelar",
    "calibration.finish": "Concluir",
    "calibration.set_position_first": "Defina a posição para iniciar a calibração.",
    "controls.cover_label": "Estore",
    "controls.tilt_label": "Inclinação",
    "controls.open": "Abrir",
    "controls.stop": "Parar",
    "controls.close": "Fechar",
    "controls.tilt_open": "Inclinar abrir",
    "controls.tilt_stop": "Inclinar parar",
    "controls.tilt_close": "Inclinar fechar",
    "hints.sequential_close.travel_time_close":
      "Comece com o estore totalmente aberto. Clique em Concluir quando o estore estiver totalmente fechado, antes de as lâminas começarem a inclinar.",
    "hints.sequential_close.travel_time_open":
      "Comece com o estore fechado e as lâminas abertas. Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.sequential_close.tilt_time_close":
      "Comece com o estore fechado mas as lâminas abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.sequential_close.tilt_time_open":
      "Comece com o estore e as lâminas fechados. Clique em Concluir quando as lâminas estiverem abertas.",
    "hints.sequential_open.travel_time_close":
      "Comece com o estore totalmente aberto e as lâminas fechadas. Clique em Concluir quando o estore estiver totalmente fechado, antes de as lâminas começarem a inclinar-se abertas.",
    "hints.sequential_open.travel_time_open":
      "Comece com o estore fechado e as lâminas fechadas. Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.sequential_open.tilt_time_close":
      "Comece com o estore fechado mas as lâminas abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.sequential_open.tilt_time_open":
      "Comece com o estore e as lâminas fechados. Clique em Concluir quando as lâminas estiverem totalmente abertas.",
    "hints.dual_motor.travel_time_close":
      "Comece com o estore aberto e as lâminas na posição segura. Clique em Concluir quando o estore estiver totalmente fechado.",
    "hints.dual_motor.travel_time_open":
      "Comece com o estore fechado e as lâminas na posição segura. Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.dual_motor.tilt_time_close":
      "Comece com o estore fechado e as lâminas abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.dual_motor.tilt_time_open":
      "Comece com o estore e as lâminas fechados. Clique em Concluir quando as lâminas estiverem totalmente abertas.",
    "hints.inline.travel_time_close":
      "Comece com o estore e as lâminas totalmente abertos. Clique em Concluir quando ambos estiverem totalmente fechados.",
    "hints.inline.travel_time_open":
      "Comece com o estore e as lâminas totalmente fechados. Clique em Concluir quando ambos estiverem totalmente abertos.",
    "hints.inline.tilt_time_close":
      "Comece com as lâminas totalmente abertas. Clique em Concluir quando as lâminas estiverem totalmente fechadas.",
    "hints.inline.tilt_time_open":
      "Comece com as lâminas totalmente fechadas. Clique em Concluir quando as lâminas estiverem totalmente abertas.",
    "hints.none.travel_time_close":
      "Clique em Concluir quando o estore estiver totalmente fechado.",
    "hints.none.travel_time_open": "Clique em Concluir quando o estore estiver totalmente aberto.",
    "hints.min_movement_time": "Clique em Concluir assim que notar o estore a mover-se.",
  },
  pl: {
    header: "Konfiguracja rolet sterowanych czasowo",
    loading: "Ładowanie...",
    saving: "Zapisywanie...",
    save_failed: "Zapis nie powiódł się — wartość przywrócona",
    confirm_cancel_calibration: "Kalibracja jest w toku. Anulować ją i kontynuować?",
    create_new: "+ Utwórz nową encję rolety",
    yaml_warning:
      "Ta encja używa konfiguracji YAML i nie może być konfigurowana z tej karty. Proszę przeprowadzić migrację do interfejsu użytkownika: Ustawienia > Urządzenia i usługi > Pomocniki > Utwórz pomocnik > Roleta sterowana czasowo.",
    load_failed: "Nie udało się załadować konfiguracji. Spróbuj ponownie.",
    admin_required:
      "Ta karta wymaga konta administratora. Zaloguj się jako administrator, aby skonfigurować rolety.",
    "tabs.device": "Urządzenie",
    "tabs.calibration": "Kalibracja",
    "control_mode.label": "Tryb sterowania",
    "control_mode.wrapped": "Opakuj istniejącą encję rolety",
    "control_mode.switch": "Przełącznik (zatrzaskowy)",
    "control_mode.pulse": "Impuls (chwilowy)",
    "control_mode.toggle": "Przełączanie (ten sam przycisk)",
    "control_mode.toggle_opposite": "Przełączanie (przeciwny przycisk)",
    "control_mode.single_button": "Jeden przycisk (cykliczny)",
    "control_mode.pulse_time": "Czas impulsu",
    "entities.cover_entity": "Encja rolety",
    "position_reporting.label": "Zgłaszanie pozycji",
    "position_reporting.reliable": "Wiarygodna informacja zwrotna o pozycji",
    "position_reporting.reliable_helper":
      "Opakowana roleta zgłasza wiarygodną pozycję i osiąga rzeczywiste krańce otwarcia/zamknięcia. Ustawienie domyślne — właściwy wybór, chyba że śledzona pozycja dryfuje względem faktycznego położenia rolety.",
    "position_reporting.unreliable": "Niewiarygodna pozycja — śledź na podstawie czasu",
    "position_reporting.unreliable_helper":
      "Śledź pozycję wyłącznie na podstawie czasu i ignoruj pozycję zgłaszaną przez roletę. Włącz tę opcję, jeśli roleta zgłasza niewiarygodną pozycję.",
    "position_reporting.no_endpoints":
      "Brak rzeczywistych krańców — zgłasza otwarta/zamknięta po zatrzymaniu",
    "position_reporting.no_endpoints_helper":
      "Dla rolet bez informacji zwrotnej o pozycji, które zgłaszają otwarta/zamknięta, gdy silnik zatrzymuje się w trakcie ruchu, a nie tylko na fizycznych krańcach. Zgłoszony stan zamknięcia zatrzymuje śledzenie na obliczonej pozycji, zamiast przeskakiwać do 0%.",
    "position_reporting.command_echo": "Stan odzwierciedla ostatnie polecenie",
    "position_reporting.command_echo_helper":
      "Włącz dla rolet (np. niektórych rolet Tuya), których stan otwarta/zamknięta/nieznana jest echem polecenia, a nie rzeczywistą pozycją końcową — nie zgłaszają przejścia otwierania/zamykania ani pozycji. Stan jest traktowany jako polecenie otwórz/zamknij/zatrzymaj, a pozycja jest śledzona na podstawie czasu.",
    "position_reporting.ignore_all": "Ignoruj wszystkie raporty urządzenia",
    "position_reporting.ignore_all_helper":
      "Stan i pozycja urządzenia są niewiarygodne. Ignoruj wszystko, co zgłasza, i śledź pozycję wyłącznie na podstawie czasów otwierania/zamykania. Home Assistant staje się jedynym sposobem poruszania roletą — obsługa za pomocą przełącznika ściennego lub pilota nie jest śledzona.",
    "position_reporting.docs_link": "Dowiedz się więcej",
    "entities.force_time_based_position": "Wymuś pozycjonowanie czasowe",
    "entities.force_time_based_position_helper":
      "Domyślnie, jeśli opakowana roleta obsługuje ustawianie pozycji, polecenie ustawienia pozycji jest wysyłane bezpośrednio do niej. Włącz tę opcję, aby zamiast tego sterować nią za pomocą czasowego otwierania/zamykania/zatrzymywania, ignorując natywną obsługę ustawiania pozycji.",
    "entities.invert": "Odwróć pozycję",
    "entities.invert_helper":
      "Odwraca oś pozycji: zgłasza 100 − pozycję opakowanej rolety i zamienia otwieranie/zamykanie. Użyj dla rolet działających odwrotnie, np. markizy, której encja bazowa zgłasza otwarte = rozwinięte. Dotyczy tylko osi pozycji; logika nachylenia pozostaje bez zmian — przeznaczone dla rolet wyłącznie pozycyjnych (markizy/rolety), a nie żaluzji z regulowanymi lamelami.",
    "entities.switch_entities": "Encje przełączników",
    "entities.open_switch": "Przełącznik otwierania",
    "entities.close_switch": "Przełącznik zamykania",
    "entities.stop_switch": "Przełącznik zatrzymania",
    "entities.switch_entities_pulse": "Encje przełączników / skryptów",
    "entities.open_switch_pulse": "Przełącznik lub skrypt otwierania",
    "entities.close_switch_pulse": "Przełącznik lub skrypt zamykania",
    "entities.stop_switch_pulse": "Przełącznik lub skrypt zatrzymania",
    "entities.button": "Przycisk",
    "tilt.label": "Nachylenie",
    "tilt.none": "Nieobsługiwane",
    "tilt.sequential_close": "Najpierw zamyka, potem nachyla zamknięte",
    "tilt.sequential_open": "Najpierw zamyka, potem nachyla otwarte",
    "tilt.dual_motor": "Osobny silnik nachylenia",
    "tilt.inline": "Nachylenie w trakcie ruchu",
    "tilt_motor.label": "Silnik nachylenia",
    "tilt_motor.open_switch": "Przełącznik otwierania nachylenia",
    "tilt_motor.close_switch": "Przełącznik zamykania nachylenia",
    "tilt_motor.stop_switch": "Przełącznik zatrzymania nachylenia",
    "tilt_motor.label_pulse": "Silnik nachylenia (przełącznik lub skrypt)",
    "tilt_motor.open_switch_pulse": "Przełącznik lub skrypt otwierania nachylenia",
    "tilt_motor.close_switch_pulse": "Przełącznik lub skrypt zamykania nachylenia",
    "tilt_motor.stop_switch_pulse": "Przełącznik lub skrypt zatrzymania nachylenia",
    "tilt_motor.safe_position": "Bezpieczna pozycja nachylenia",
    "tilt_motor.safe_position_helper":
      "Nachylenie przesuwa się tu przed ruchem (100 = w pełni otwarte)",
    "tilt_motor.max_allowed_position": "Maks. dozwolona pozycja nachylenia (opcjonalna)",
    "tilt_motor.max_allowed_helper":
      "Nachylenie dozwolone tylko gdy pozycja rolety wynosi tyle lub mniej (0 = zamknięta, 100 = otwarta)",
    "tilt.close_includes_tilt": "Zamknięcie rolety zamyka również lamele",
    "tilt.close_includes_tilt_helper":
      "Podczas zamykania lamele nachylają się do pozycji zamkniętej na końcu ruchu",
    "assumed_state.label": "Stan zakładany",
    "assumed_state.helper":
      "Gdy włączone, Home Assistant traktuje pozycję jako szacowaną i pozostawia aktywne przyciski otwierania i zamykania. Wyłącz, jeśli ufasz obliczeniom czasowym i chcesz, aby interfejs wyszarzał niedostępne akcje (np. zamknięcie, gdy roleta jest już zamknięta).",
    "relay_reports_off.label": "Przekaźnik zgłasza własne wyłączenie",
    "relay_reports_off.helper":
      "Pozostaw włączone dla zwykłych przekaźników przełączających, które same się wyłączają po impulsie i to zgłaszają. Wyłącz dla modułów impulsowych zarządzanych sprzętowo (np. Aqara T2), które pulsują wewnętrznie, ale nigdy nie zgłaszają wyłączenia, pozostawiając encję przełącznika zablokowaną w stanie włączonym. Po wyłączeniu integracja wysyła tylko jedno polecenie WŁĄCZ na naciśnięcie i nigdy WYŁĄCZ — dzięki czemu każde naciśnięcie to dokładnie jedna czysta aktywacja, bez podwojonych poleceń.",
    "send_endpoint_stop.label": "Wysyłaj sygnał zatrzymania na krańcach",
    "send_endpoint_stop.helper":
      "Gdy roleta osiągnie pełne otwarcie lub zamknięcie, wyślij impuls zatrzymania. Pozostaw włączone dla sterowników, które działają, dopóki nie otrzymają zatrzymania (w przeciwnym razie roleta blokuje się, a fizyczne przyciski przestają reagować). Wyłącz, jeśli silnik sam zatrzymuje się na krańcach, a dodatkowe zatrzymanie powoduje przejście do zaprogramowanej/ulubionej pozycji.",
    "force_endpoint_redrive.label": "Zawsze ponownie wysyłaj otwórz/zamknij na krańcach",
    "force_endpoint_redrive.helper":
      "Dla rolet bez informacji zwrotnej o pozycji, które mogą być sterowane również zewnętrznym pilotem, przez co Home Assistant może błędnie sądzić, że są już całkowicie otwarte lub zamknięte. Po włączeniu polecenie otwarcia lub zamknięcia jest zawsze wykonywane przez pełny czas ruchu, nawet jeśli Home Assistant sądzi, że roleta już tam jest — dzięki czemu polecenie na pewno dotrze do silnika. Pozostaw wyłączone dla rolet zgłaszających własną pozycję.",
    "wait_for_relay_feedback.label": "Czekaj na potwierdzenie przekaźnika przed śledzeniem",
    "wait_for_relay_feedback.helper":
      "Uruchamia licznik czasu pozycji, gdy przekaźnik zgłosi, że się włączył, zamiast w chwili wysłania polecenia. W wolnej lub wychłodzonej sieci Zigbee/Z-Wave polecenie może docierać do przekaźnika przez kilka sekund; bez tej opcji to opóźnienie jest liczone jako ruch, a śledzona pozycja wyprzedza roletę. Pozostaw wyłączone, chyba że pozycja dryfuje w roletach, których przekaźnik reaguje wolno.",
    "recalibrate_before_position.label": "Otwórz w pełni przed przejściem do pozycji (Beta)",
    "recalibrate_before_position.helper":
      "Dla rolet bez informacji zwrotnej o pozycji, które mogą być poruszane również pilotem. Przed każdym poleceniem ustawienia pozycji najpierw otwiera roletę w pełni, dzięki czemu ruch zaczyna się od znanej pozycji, a nie od nieaktualnego przybliżenia. Z grubsza podwaja czas ruchu przy każdym przesunięciu, a przy nachyleniu w trakcie ruchu lub nachyleniu sekwencyjnym regulacja listew porusza także samą roletę.",
    "resync.label": "Resynchronizacja",
    "resync.helper":
      "Poinformuj integrację o rzeczywistej pozycji rolety po tym, jak została poruszona fizycznym przyciskiem lub pilotem RF. To ponownie zakotwicza śledzenie pozycji i zatrzymuje silnik, jeśli Home Assistant nadal nim steruje; nigdy go nie uruchamia.",
    more_info: "Więcej informacji",
    "timing.travel_attribute_header": "Atrybut ruchu",
    "timing.tilt_attribute_header": "Atrybut nachylenia",
    "timing.value_header": "Wartość",
    "timing.not_set": "Nieustawione",
    "timing.travel_time_close": "Czas ruchu (zamykanie)",
    "timing.travel_time_open": "Czas ruchu (otwieranie)",
    "timing.travel_startup_delay": "Opóźnienie startu ruchu",
    "timing.tilt_time_close": "Czas nachylenia (zamykanie)",
    "timing.tilt_time_open": "Czas nachylenia (otwieranie)",
    "timing.tilt_startup_delay": "Opóźnienie startu nachylenia",
    "timing.min_movement_time": "Minimalny czas ruchu",
    "timing.endpoint_runon_time": "Czas dobiegu na krańcach",
    "position.label": "Aktualna pozycja",
    "position.helper": "Przesuń roletę do znanego krańca, a następnie ustaw pozycję.",
    "position.unknown": "Nieznana",
    "position.open": "W pełni otwarta",
    "position.closed": "W pełni zamknięta",
    "position.closed_tilt_open": "W pełni zamknięta, nachylenie otwarte",
    "position.closed_tilt_closed": "W pełni zamknięta, nachylenie zamknięte",
    "calibration.label": "Kalibracja czasowa",
    "calibration.attribute_label": "Atrybut",
    "calibration.start": "Rozpocznij",
    "calibration.active": "Kalibracja aktywna",
    "calibration.step": "Krok {step}",
    "calibration.final_step": "Krok końcowy",
    "calibration.cancel": "Anuluj",
    "calibration.finish": "Zakończ",
    "calibration.set_position_first": "Ustaw pozycję, aby rozpocząć kalibrację.",
    "controls.cover_label": "Roleta",
    "controls.tilt_label": "Nachylenie",
    "controls.open": "Otwórz",
    "controls.stop": "Zatrzymaj",
    "controls.close": "Zamknij",
    "controls.tilt_open": "Otwórz nachylenie",
    "controls.tilt_stop": "Zatrzymaj nachylenie",
    "controls.tilt_close": "Zamknij nachylenie",
    "hints.sequential_close.travel_time_close":
      "Zacznij z roletą w pełni otwartą. Kliknij Zakończ, gdy roleta jest w pełni zamknięta, zanim listwy zaczną się nachylać.",
    "hints.sequential_close.travel_time_open":
      "Zacznij z zamkniętą roletą i otwartymi listwami. Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.sequential_close.tilt_time_close":
      "Zacznij z zamkniętą roletą, ale otwartymi listwami. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.sequential_close.tilt_time_open":
      "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy listwy są otwarte.",
    "hints.sequential_open.travel_time_close":
      "Zacznij z roletą w pełni otwartą i zamkniętymi listwami. Kliknij Zakończ, gdy roleta jest w pełni zamknięta, zanim listwy zaczną się nachylać otwarte.",
    "hints.sequential_open.travel_time_open":
      "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.sequential_open.tilt_time_close":
      "Zacznij z zamkniętą roletą, ale otwartymi listwami. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.sequential_open.tilt_time_open":
      "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy listwy są w pełni otwarte.",
    "hints.dual_motor.travel_time_close":
      "Zacznij z otwartą roletą i listwami w bezpiecznej pozycji. Kliknij Zakończ, gdy roleta jest w pełni zamknięta.",
    "hints.dual_motor.travel_time_open":
      "Zacznij z zamkniętą roletą i listwami w bezpiecznej pozycji. Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.dual_motor.tilt_time_close":
      "Zacznij z zamkniętą roletą i otwartymi listwami. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.dual_motor.tilt_time_open":
      "Zacznij z zamkniętą roletą i zamkniętymi listwami. Kliknij Zakończ, gdy listwy są w pełni otwarte.",
    "hints.inline.travel_time_close":
      "Zacznij z roletą i listwami w pełni otwartymi. Kliknij Zakończ, gdy obie są w pełni zamknięte.",
    "hints.inline.travel_time_open":
      "Zacznij z roletą i listwami w pełni zamkniętymi. Kliknij Zakończ, gdy obie są w pełni otwarte.",
    "hints.inline.tilt_time_close":
      "Zacznij z listwami w pełni otwartymi. Kliknij Zakończ, gdy listwy są w pełni zamknięte.",
    "hints.inline.tilt_time_open":
      "Zacznij z listwami w pełni zamkniętymi. Kliknij Zakończ, gdy listwy są w pełni otwarte.",
    "hints.none.travel_time_close": "Kliknij Zakończ, gdy roleta jest w pełni zamknięta.",
    "hints.none.travel_time_open": "Kliknij Zakończ, gdy roleta jest w pełni otwarta.",
    "hints.min_movement_time": "Kliknij Zakończ, gdy tylko zauważysz ruch rolety.",
  },
  de: {
    header: "Konfiguration von Cover Time Based",
    loading: "Wird geladen...",
    saving: "Wird gespeichert...",
    save_failed: "Speichern fehlgeschlagen — Wert zurückgesetzt",
    confirm_cancel_calibration: "Eine Kalibrierung läuft. Abbrechen und fortfahren?",
    create_new: "+ Neue Rollladen-Entität anlegen",
    yaml_warning:
      "Diese Entität verwendet eine YAML-Konfiguration und kann nicht über diese Karte konfiguriert werden. Bitte migriere sie auf die Benutzeroberfläche: Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → Cover Time Based.",
    load_failed: "Laden der Konfiguration fehlgeschlagen. Bitte versuche es erneut.",
    admin_required:
      "Diese Karte benötigt ein Administratorkonto. Melde dich als Administrator an, um Rollläden zu konfigurieren.",
    "tabs.device": "Gerät",
    "tabs.calibration": "Kalibrierung",
    "control_mode.label": "Steuerungsmodus",
    "control_mode.wrapped": "Eine vorhandene Rollladen-Entität einbinden",
    "control_mode.switch": "Schalter (rastend)",
    "control_mode.pulse": "Impuls (tastend)",
    "control_mode.toggle": "Umschalten (gleiche Taste)",
    "control_mode.toggle_opposite": "Umschalten (entgegengesetzte Taste)",
    "control_mode.single_button": "Einzelne Taste (zyklisch)",
    "control_mode.pulse_time": "Impulsdauer",
    "entities.cover_entity": "Rollladen-Entität",
    "position_reporting.label": "Positionsmeldung",
    "position_reporting.reliable": "Zuverlässige Positionsrückmeldung",
    "position_reporting.reliable_helper":
      "Der eingebundene Rollladen meldet eine zuverlässige Position und erreicht seine echten Endlagen offen/geschlossen. Der Standard — die richtige Wahl, sofern die verfolgte Position nicht von der tatsächlichen Position des Rollladens abdriftet.",
    "position_reporting.unreliable": "Position unzuverlässig — über die Zeit verfolgen",
    "position_reporting.unreliable_helper":
      "Die Position ausschließlich über die Zeit verfolgen und die vom eingebundenen Rollladen gemeldete Position ignorieren. Aktiviere dies, wenn der zugrunde liegende Rollladen eine unzuverlässige Position meldet.",
    "position_reporting.no_endpoints":
      "Keine echten Endlagen — meldet offen/geschlossen beim Stoppen",
    "position_reporting.no_endpoints_helper":
      "Für Rollläden ohne Positionsrückmeldung, die offen/geschlossen melden, wenn der Motor mitten in der Fahrt stoppt, statt nur an den physischen Endlagen. Ein als geschlossen gemeldeter Zustand beendet die Verfolgung an der berechneten Position, statt auf 0% zu springen.",
    "position_reporting.command_echo": "Zustand spiegelt den letzten Befehl",
    "position_reporting.command_echo_helper":
      "Aktiviere dies für Rollläden (z. B. manche Tuya-Rollläden), deren Zustand offen/geschlossen/unbekannt nur ein Echo des Befehls statt einer echten Endlage ist — sie melden weder einen Öffnungs-/Schließvorgang noch eine Position. Der Zustand wird als Öffnen-/Schließen-/Stopp-Befehl behandelt und die Position über die Zeit verfolgt.",
    "position_reporting.ignore_all": "Alle Gerätemeldungen ignorieren",
    "position_reporting.ignore_all_helper":
      "Zustand und Position des Geräts sind allesamt unzuverlässig. Ignoriere alles, was es meldet, und verfolge die Position ausschließlich über die Öffnungs-/Schließzeiten. Home Assistant wird die einzige Möglichkeit, den Rollladen zu bewegen — eine Bedienung über Wandschalter oder Fernbedienung wird nicht verfolgt.",
    "position_reporting.docs_link": "Mehr erfahren",
    "entities.force_time_based_position": "Zeitbasierte Positionierung erzwingen",
    "entities.force_time_based_position_helper":
      "Standardmäßig wird der Positionsbefehl direkt an den eingebundenen Rollladen gesendet, sofern dieser das Setzen einer Position unterstützt. Aktiviere dies, um ihn stattdessen mit zeitgesteuertem Öffnen/Schließen/Stoppen zu fahren und seine native Positionsunterstützung zu ignorieren.",
    "entities.invert": "Position invertieren",
    "entities.invert_helper":
      "Kehrt die Positionsachse um: meldet 100 − die Position des eingebundenen Rollladens und vertauscht Öffnen/Schließen. Verwende dies für Rollläden, die verkehrt herum laufen, z. B. eine Markise, deren zugrunde liegende Entität offen = ausgefahren meldet. Betrifft nur die Positionsachse; die Neigungslogik bleibt unverändert — gedacht für Behänge, die nur eine Position kennen (Markisen/Rollläden), nicht für Jalousien mit verstellbaren Lamellen.",
    "entities.switch_entities": "Schalter-Entitäten",
    "entities.open_switch": "Schalter zum Öffnen",
    "entities.close_switch": "Schalter zum Schließen",
    "entities.stop_switch": "Schalter zum Stoppen",
    "entities.switch_entities_pulse": "Schalter- / Skript-Entitäten",
    "entities.open_switch_pulse": "Schalter oder Skript zum Öffnen",
    "entities.close_switch_pulse": "Schalter oder Skript zum Schließen",
    "entities.stop_switch_pulse": "Schalter oder Skript zum Stoppen",
    "entities.button": "Taste",
    "tilt.label": "Neigungsmodus",
    "tilt.none": "Nicht unterstützt",
    "tilt.sequential_close": "Schließt, dann schließt die Neigung",
    "tilt.sequential_open": "Schließt, dann öffnet die Neigung",
    "tilt.dual_motor": "Separater Neigungsmotor",
    "tilt.inline": "Neigt während der Fahrt",
    "tilt_motor.label": "Neigungsmotor",
    "tilt_motor.open_switch": "Schalter zum Öffnen der Neigung",
    "tilt_motor.close_switch": "Schalter zum Schließen der Neigung",
    "tilt_motor.stop_switch": "Schalter zum Stoppen der Neigung",
    "tilt_motor.label_pulse": "Neigungsmotor (Schalter oder Skript)",
    "tilt_motor.open_switch_pulse": "Schalter oder Skript zum Öffnen der Neigung",
    "tilt_motor.close_switch_pulse": "Schalter oder Skript zum Schließen der Neigung",
    "tilt_motor.stop_switch_pulse": "Schalter oder Skript zum Stoppen der Neigung",
    "tilt_motor.safe_position": "Sichere Neigungsposition",
    "tilt_motor.safe_position_helper":
      "Die Neigung fährt vor der Fahrt hierhin (100 = vollständig geöffnet)",
    "tilt_motor.max_allowed_position": "Maximal erlaubte Neigungsposition (optional)",
    "tilt_motor.max_allowed_helper":
      "Neigen ist nur erlaubt, wenn die Rollladenposition auf oder unter diesem Wert liegt (0 = geschlossen, 100 = offen)",
    "tilt.close_includes_tilt": "Schließen des Rollladens schließt auch die Lamellen",
    "tilt.close_includes_tilt_helper":
      "Beim Schließen neigen sich die Lamellen am Ende der Fahrt zu",
    "assumed_state.label": "Angenommener Zustand",
    "assumed_state.helper":
      "Wenn aktiviert, behandelt Home Assistant die Position als geschätzt und hält die Bedienelemente zum Öffnen und Schließen aktiv. Deaktiviere dies, wenn du der zeitbasierten Berechnung vertraust und möchtest, dass die Oberfläche nicht verfügbare Aktionen ausgraut (z. B. Schließen, wenn bereits geschlossen).",
    "relay_reports_off.label": "Relais meldet sein eigenes AUS",
    "relay_reports_off.helper":
      "Für gewöhnliche Relais im Umschaltbetrieb aktiviert lassen: Sie schalten sich nach dem Impuls selbst ab und melden das auch. Deaktiviere dies für hardwaregesteuerte Impulsmodule (z. B. Aqara T2), die intern pulsen, aber nie melden, wenn sie abschalten, sodass die Schalter-Entität dauerhaft auf „an“ hängen bleibt. Deaktiviert sendet die Integration pro Tastendruck nur ein einziges EIN und nie ein AUS — jeder Tastendruck ist also genau eine saubere Auslösung, ohne doppelte Befehle.",
    "send_endpoint_stop.label": "Stopp-Signal an den Endlagen senden",
    "send_endpoint_stop.helper":
      "Sendet den Stopp-Impuls, sobald dein Rollladen vollständig geöffnet oder geschlossen ist. Für Steuerungen aktiviert lassen, die weiterlaufen, bis sie einen Stopp erhalten (sonst bleibt der Rollladen hängen und die physischen Tasten reagieren nicht mehr). Deaktiviere dies, wenn dein Motor an seinen Endlagen selbst stoppt und ein zusätzlicher Stopp ihn in eine voreingestellte Favoritenposition fahren lässt.",
    "force_endpoint_redrive.label": "Öffnen/Schließen an den Endlagen immer erneut senden",
    "force_endpoint_redrive.helper":
      "Für Rollläden ohne Positionsrückmeldung, die sich zusätzlich per externer Fernbedienung bewegen lassen, sodass Home Assistant fälschlich annehmen kann, sie seien bereits vollständig geöffnet oder geschlossen. Wenn aktiviert, wird ein Öffnen- oder Schließen-Befehl immer über die volle Fahrzeit ausgeführt, selbst wenn Home Assistant den Rollladen dort schon vermutet — so erreicht der Befehl garantiert den Motor. Für Rollläden, die ihre eigene Position melden, deaktiviert lassen.",
    "wait_for_relay_feedback.label": "Vor dem Verfolgen auf die Relais-Bestätigung warten",
    "wait_for_relay_feedback.helper":
      "Startet den Positionszeitgeber, wenn das Relais sein Einschalten meldet, statt im Moment des Befehlsversands. In einem langsamen oder kalten Zigbee-/Z-Wave-Mesh kann der Befehl mehrere Sekunden bis zum Relais brauchen; ohne diese Option wird diese Verzögerung als Fahrt gezählt und die verfolgte Position läuft dem Rollladen voraus. Lass die Option aus, sofern die Position bei Rollläden mit langsam reagierendem Relais nicht abdriftet.",
    "recalibrate_before_position.label":
      "Vor einer Positionsfahrt zuerst vollständig öffnen (Beta)",
    "recalibrate_before_position.helper":
      "Für Rollläden ohne Positionsrückmeldung, die sich auch per Fernbedienung bewegen lassen. Fährt den Rollladen vor jedem Positionsbefehl zuerst vollständig auf, sodass die Fahrt von einer bekannten Position statt von einer abgedrifteten Schätzung beginnt. Verdoppelt dadurch etwa die Fahrzeit jeder Fahrt, und bei Neigung während der Fahrt oder bei sequenzieller Neigung bewegt sich der Rollladen mit, sobald du die Lamellen verstellst.",
    "resync.label": "Neuausrichtung",
    "resync.helper":
      "Teile der Integration die tatsächliche Position des Rollladens mit, nachdem er über die physische Taste oder eine RF-Fernbedienung bewegt wurde. Dies verankert die Positionsverfolgung neu und stoppt den Motor, falls Home Assistant ihn noch ansteuert; gestartet wird er dabei nie.",
    more_info: "Weitere Informationen",
    "timing.travel_attribute_header": "Fahrattribut",
    "timing.tilt_attribute_header": "Neigungsattribut",
    "timing.value_header": "Wert",
    "timing.not_set": "Nicht gesetzt",
    "timing.travel_time_close": "Fahrzeit (Schließen)",
    "timing.travel_time_open": "Fahrzeit (Öffnen)",
    "timing.travel_startup_delay": "Anlaufverzögerung der Fahrt",
    "timing.tilt_time_close": "Neigungszeit (Schließen)",
    "timing.tilt_time_open": "Neigungszeit (Öffnen)",
    "timing.tilt_startup_delay": "Anlaufverzögerung der Neigung",
    "timing.min_movement_time": "Minimale Bewegungszeit",
    "timing.endpoint_runon_time": "Nachlaufzeit an den Endlagen",
    "position.label": "Aktuelle Position",
    "position.helper": "Fahre den Rollladen in eine bekannte Endlage und setze dann die Position.",
    "position.unknown": "Unbekannt",
    "position.open": "Vollständig geöffnet",
    "position.closed": "Vollständig geschlossen",
    "position.closed_tilt_open": "Vollständig geschlossen, Neigung offen",
    "position.closed_tilt_closed": "Vollständig geschlossen, Neigung geschlossen",
    "calibration.label": "Zeitkalibrierung",
    "calibration.attribute_label": "Attribut",
    "calibration.start": "Starten",
    "calibration.active": "Kalibrierung aktiv",
    "calibration.step": "Schritt {step}",
    "calibration.final_step": "Letzter Schritt",
    "calibration.cancel": "Abbrechen",
    "calibration.finish": "Fertig",
    "calibration.set_position_first": "Setze die Position, um die Kalibrierung zu starten.",
    "controls.cover_label": "Rollladen",
    "controls.tilt_label": "Neigung",
    "controls.open": "Öffnen",
    "controls.stop": "Stopp",
    "controls.close": "Schließen",
    "controls.tilt_open": "Neigung öffnen",
    "controls.tilt_stop": "Neigung stoppen",
    "controls.tilt_close": "Neigung schließen",
    "hints.sequential_close.travel_time_close":
      "Beginne mit vollständig geöffnetem Rollladen. Klicke auf Fertig, wenn der Rollladen vollständig geschlossen ist, bevor sich die Lamellen zu neigen beginnen.",
    "hints.sequential_close.travel_time_open":
      "Beginne mit geschlossenem Rollladen und offenen Lamellen. Klicke auf Fertig, wenn der Rollladen vollständig geöffnet ist.",
    "hints.sequential_close.tilt_time_close":
      "Beginne mit geschlossenem Rollladen, aber offenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig geschlossen sind.",
    "hints.sequential_close.tilt_time_open":
      "Beginne mit geschlossenem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn die Lamellen offen sind.",
    "hints.sequential_open.travel_time_close":
      "Beginne mit vollständig geöffnetem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn der Rollladen vollständig geschlossen ist, bevor sich die Lamellen zu öffnen beginnen.",
    "hints.sequential_open.travel_time_open":
      "Beginne mit geschlossenem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn der Rollladen vollständig geöffnet ist.",
    "hints.sequential_open.tilt_time_close":
      "Beginne mit geschlossenem Rollladen, aber offenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig geschlossen sind.",
    "hints.sequential_open.tilt_time_open":
      "Beginne mit geschlossenem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig offen sind.",
    "hints.dual_motor.travel_time_close":
      "Beginne mit geöffnetem Rollladen und Lamellen in der sicheren Position. Klicke auf Fertig, wenn der Rollladen vollständig geschlossen ist.",
    "hints.dual_motor.travel_time_open":
      "Beginne mit geschlossenem Rollladen und Lamellen in der sicheren Position. Klicke auf Fertig, wenn der Rollladen vollständig geöffnet ist.",
    "hints.dual_motor.tilt_time_close":
      "Beginne mit geschlossenem Rollladen und offenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig geschlossen sind.",
    "hints.dual_motor.tilt_time_open":
      "Beginne mit geschlossenem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig offen sind.",
    "hints.inline.travel_time_close":
      "Beginne mit vollständig geöffnetem Rollladen und offenen Lamellen. Klicke auf Fertig, wenn beide vollständig geschlossen sind.",
    "hints.inline.travel_time_open":
      "Beginne mit vollständig geschlossenem Rollladen und geschlossenen Lamellen. Klicke auf Fertig, wenn beide vollständig geöffnet sind.",
    "hints.inline.tilt_time_close":
      "Beginne mit vollständig offenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig geschlossen sind.",
    "hints.inline.tilt_time_open":
      "Beginne mit vollständig geschlossenen Lamellen. Klicke auf Fertig, wenn die Lamellen vollständig offen sind.",
    "hints.none.travel_time_close":
      "Klicke auf Fertig, wenn der Rollladen vollständig geschlossen ist.",
    "hints.none.travel_time_open":
      "Klicke auf Fertig, wenn der Rollladen vollständig geöffnet ist.",
    "hints.min_movement_time":
      "Klicke auf Fertig, sobald du bemerkst, dass sich der Rollladen bewegt.",
  },
  it: {
    header: "Configurazione di Cover Time Based",
    loading: "Caricamento...",
    saving: "Salvataggio...",
    save_failed: "Salvataggio non riuscito — valore ripristinato",
    confirm_cancel_calibration: "È in corso una calibrazione. Annullarla e continuare?",
    create_new: "+ Crea una nuova entità tapparella",
    yaml_warning:
      "Questa entità utilizza la configurazione YAML e non può essere configurata da questa scheda. Esegui la migrazione all'interfaccia utente: Impostazioni → Dispositivi e servizi → Helper → Crea helper → Cover Time Based.",
    load_failed: "Caricamento della configurazione non riuscito. Riprova.",
    admin_required:
      "Questa scheda richiede un account amministratore. Accedi come amministratore per configurare le tapparelle.",
    "tabs.device": "Dispositivo",
    "tabs.calibration": "Calibrazione",
    "control_mode.label": "Modalità di controllo",
    "control_mode.wrapped": "Incapsula un'entità tapparella esistente",
    "control_mode.switch": "Interruttore (mantenuto)",
    "control_mode.pulse": "Impulso (momentaneo)",
    "control_mode.toggle": "Commutazione (stesso pulsante)",
    "control_mode.toggle_opposite": "Commutazione (pulsante opposto)",
    "control_mode.single_button": "Pulsante singolo (ciclico)",
    "control_mode.pulse_time": "Durata dell'impulso",
    "entities.cover_entity": "Entità tapparella",
    "position_reporting.label": "Segnalazione della posizione",
    "position_reporting.reliable": "Retroazione di posizione affidabile",
    "position_reporting.reliable_helper":
      "La tapparella incapsulata riporta una posizione affidabile e raggiunge i suoi veri finecorsa di apertura/chiusura. È l'impostazione predefinita — la scelta giusta a meno che la posizione tracciata non vada alla deriva rispetto a dove si trova realmente la tapparella.",
    "position_reporting.unreliable": "Posizione non affidabile — traccia in base al tempo",
    "position_reporting.unreliable_helper":
      "Traccia la posizione solo in base al tempo e ignora la posizione riportata dalla tapparella incapsulata. Attiva questa opzione se la tapparella sottostante riporta una posizione non affidabile.",
    "position_reporting.no_endpoints":
      "Nessun finecorsa reale — riporta aperta/chiusa quando è ferma",
    "position_reporting.no_endpoints_helper":
      "Per le tapparelle senza retroazione di posizione che riportano aperta/chiusa quando il motore si ferma a metà corsa anziché solo ai finecorsa fisici. Uno stato di chiusura riportato interrompe il tracciamento alla posizione calcolata anziché saltare a 0%.",
    "position_reporting.command_echo": "Lo stato rispecchia l'ultimo comando",
    "position_reporting.command_echo_helper":
      "Attiva questa opzione per le tapparelle (ad esempio alcune tapparelle Tuya) il cui stato aperto/chiuso/sconosciuto è l'eco di un comando anziché un vero finecorsa — non riportano alcuna transizione di apertura/chiusura né alcuna posizione. Lo stato viene trattato come un comando di apertura/chiusura/arresto e la posizione viene tracciata in base al tempo.",
    "position_reporting.ignore_all": "Ignora tutte le segnalazioni del dispositivo",
    "position_reporting.ignore_all_helper":
      "Lo stato e la posizione del dispositivo sono tutti inaffidabili. Ignora tutto ciò che segnala e traccia la posizione solo in base ai tempi di apertura/chiusura. Home Assistant diventa l'unico modo per muovere la tapparella — l'azionamento tramite interruttore a parete o telecomando non viene tracciato.",
    "position_reporting.docs_link": "Scopri di più",
    "entities.force_time_based_position": "Forza il posizionamento basato sul tempo",
    "entities.force_time_based_position_helper":
      "Per impostazione predefinita, se la tapparella incapsulata supporta l'impostazione della posizione, il comando di posizionamento le viene inviato direttamente. Attiva questa opzione per comandarla invece con apertura/chiusura/arresto temporizzati, ignorando il suo supporto nativo al posizionamento.",
    "entities.invert": "Inverti la posizione",
    "entities.invert_helper":
      "Inverte l'asse della posizione: riporta 100 − la posizione della tapparella incapsulata e scambia apertura/chiusura. Usa questa opzione per le tapparelle che funzionano al contrario, ad esempio una tenda da sole la cui entità sottostante riporta aperta = estesa. Riguarda solo l'asse della posizione; la logica di inclinazione resta invariata — è pensata per coperture con la sola posizione (tende da sole/tapparelle), non per veneziane con lamelle orientabili.",
    "entities.switch_entities": "Entità interruttore",
    "entities.open_switch": "Interruttore di apertura",
    "entities.close_switch": "Interruttore di chiusura",
    "entities.stop_switch": "Interruttore di arresto",
    "entities.switch_entities_pulse": "Entità interruttore / script",
    "entities.open_switch_pulse": "Interruttore o script di apertura",
    "entities.close_switch_pulse": "Interruttore o script di chiusura",
    "entities.stop_switch_pulse": "Interruttore o script di arresto",
    "entities.button": "Pulsante",
    "tilt.label": "Modalità di inclinazione",
    "tilt.none": "Non supportata",
    "tilt.sequential_close": "Chiude, poi inclina in chiusura",
    "tilt.sequential_open": "Chiude, poi inclina in apertura",
    "tilt.dual_motor": "Motore di inclinazione separato",
    "tilt.inline": "Si inclina durante la corsa",
    "tilt_motor.label": "Motore di inclinazione",
    "tilt_motor.open_switch": "Interruttore di apertura dell'inclinazione",
    "tilt_motor.close_switch": "Interruttore di chiusura dell'inclinazione",
    "tilt_motor.stop_switch": "Interruttore di arresto dell'inclinazione",
    "tilt_motor.label_pulse": "Motore di inclinazione (interruttore o script)",
    "tilt_motor.open_switch_pulse": "Interruttore o script di apertura dell'inclinazione",
    "tilt_motor.close_switch_pulse": "Interruttore o script di chiusura dell'inclinazione",
    "tilt_motor.stop_switch_pulse": "Interruttore o script di arresto dell'inclinazione",
    "tilt_motor.safe_position": "Posizione di inclinazione sicura",
    "tilt_motor.safe_position_helper":
      "L'inclinazione si porta qui prima della corsa (100 = completamente aperta)",
    "tilt_motor.max_allowed_position": "Posizione di inclinazione massima consentita (facoltativa)",
    "tilt_motor.max_allowed_helper":
      "L'inclinazione è consentita solo quando la posizione della tapparella è pari o inferiore a questo valore (0 = chiusa, 100 = aperta)",
    "tilt.close_includes_tilt": "La chiusura della tapparella chiude anche le lamelle",
    "tilt.close_includes_tilt_helper":
      "In chiusura, le lamelle si inclinano fino a chiudersi al termine della corsa",
    "assumed_state.label": "Stato presunto",
    "assumed_state.helper":
      "Quando è attivo, Home Assistant considera la posizione come stimata e mantiene attivi sia il comando di apertura sia quello di chiusura. Disattivalo se ti fidi del calcolo basato sul tempo e vuoi che l'interfaccia disattivi le azioni non disponibili (ad esempio chiudere quando è già chiusa).",
    "relay_reports_off.label": "Il relè segnala il proprio spegnimento",
    "relay_reports_off.helper":
      "Lascialo attivo per i normali relè a commutazione, che si spengono da soli dopo l'impulso e lo segnalano. Disattivalo per i moduli a impulso gestiti via hardware (ad esempio Aqara T2) che generano l'impulso internamente ma non segnalano mai quando si spengono, lasciando l'entità interruttore bloccata su acceso. Con l'opzione disattivata, l'integrazione invia un solo comando di accensione per ogni pressione e mai uno di spegnimento — così ogni pressione è esattamente un'attivazione pulita, senza comandi duplicati.",
    "send_endpoint_stop.label": "Invia il segnale di arresto ai finecorsa",
    "send_endpoint_stop.helper":
      "Quando la tapparella raggiunge l'apertura o la chiusura completa, invia l'impulso di arresto. Mantienilo attivo per le centraline che continuano a funzionare finché non ricevono un arresto (altrimenti la tapparella si blocca e i pulsanti fisici smettono di rispondere). Disattivalo se il motore si ferma da solo ai finecorsa e un arresto aggiuntivo lo fa spostare su una posizione preimpostata/preferita.",
    "force_endpoint_redrive.label": "Invia sempre di nuovo apertura/chiusura ai finecorsa",
    "force_endpoint_redrive.helper":
      "Per le tapparelle senza retroazione di posizione che possono essere azionate anche da un telecomando esterno, per cui Home Assistant potrebbe credere erroneamente che siano già completamente aperte o chiuse. Quando è attivo, un comando di apertura o chiusura viene sempre eseguito per l'intero tempo di corsa anche se Home Assistant ritiene che la tapparella si trovi già lì — garantendo che il comando raggiunga il motore. Lascialo disattivato per le tapparelle che riportano la propria posizione.",
    "wait_for_relay_feedback.label": "Attendi la conferma del relè prima di tracciare",
    "wait_for_relay_feedback.helper":
      "Avvia il timer di posizione quando il relè segnala di essersi acceso, anziché nel momento in cui viene inviato il comando. Su una rete mesh Zigbee/Z-Wave lenta o fredda il comando può impiegare alcuni secondi a raggiungere il relè; senza questa opzione, quel ritardo viene conteggiato come corsa e la posizione tracciata precede la tapparella. Lascialo disattivato, a meno che la posizione non vada alla deriva su tapparelle il cui relè risponde lentamente.",
    "recalibrate_before_position.label": "Apri completamente prima di spostare in posizione (Beta)",
    "recalibrate_before_position.helper":
      "Per le tapparelle senza retroazione di posizione che possono essere spostate anche da un telecomando. Porta la tapparella in apertura completa prima di ogni comando di posizionamento, così il movimento parte da una posizione nota anziché da una stima alla deriva. Raddoppia circa il tempo di corsa di ogni movimento e, con l'inclinazione durante la corsa o quella sequenziale, muove la tapparella anche quando regoli le lamelle.",
    "resync.label": "Risincronizza",
    "resync.helper":
      "Comunica all'integrazione la posizione reale della tapparella dopo che è stata mossa con il pulsante fisico o un telecomando RF. Questo riancora il tracciamento della posizione e ferma il motore se Home Assistant lo sta ancora comandando; non lo avvia mai.",
    more_info: "Maggiori informazioni",
    "timing.travel_attribute_header": "Attributo di corsa",
    "timing.tilt_attribute_header": "Attributo di inclinazione",
    "timing.value_header": "Valore",
    "timing.not_set": "Non impostato",
    "timing.travel_time_close": "Tempo di corsa (chiusura)",
    "timing.travel_time_open": "Tempo di corsa (apertura)",
    "timing.travel_startup_delay": "Ritardo di avvio della corsa",
    "timing.tilt_time_close": "Tempo di inclinazione (chiusura)",
    "timing.tilt_time_open": "Tempo di inclinazione (apertura)",
    "timing.tilt_startup_delay": "Ritardo di avvio dell'inclinazione",
    "timing.min_movement_time": "Tempo minimo di movimento",
    "timing.endpoint_runon_time": "Tempo di extracorsa al finecorsa",
    "position.label": "Posizione attuale",
    "position.helper": "Porta la tapparella a un finecorsa noto, poi imposta la posizione.",
    "position.unknown": "Sconosciuta",
    "position.open": "Completamente aperta",
    "position.closed": "Completamente chiusa",
    "position.closed_tilt_open": "Completamente chiusa, inclinazione aperta",
    "position.closed_tilt_closed": "Completamente chiusa, inclinazione chiusa",
    "calibration.label": "Calibrazione dei tempi",
    "calibration.attribute_label": "Attributo",
    "calibration.start": "Avvia",
    "calibration.active": "Calibrazione attiva",
    "calibration.step": "Passo {step}",
    "calibration.final_step": "Passo finale",
    "calibration.cancel": "Annulla",
    "calibration.finish": "Fine",
    "calibration.set_position_first": "Imposta la posizione per avviare la calibrazione.",
    "controls.cover_label": "Tapparella",
    "controls.tilt_label": "Inclinazione",
    "controls.open": "Apri",
    "controls.stop": "Ferma",
    "controls.close": "Chiudi",
    "controls.tilt_open": "Apri inclinazione",
    "controls.tilt_stop": "Ferma inclinazione",
    "controls.tilt_close": "Chiudi inclinazione",
    "hints.sequential_close.travel_time_close":
      "Parti con la tapparella completamente aperta. Clicca su Fine quando la tapparella è completamente chiusa, prima che le lamelle inizino a inclinarsi.",
    "hints.sequential_close.travel_time_open":
      "Parti con la tapparella chiusa e le lamelle aperte. Clicca su Fine quando la tapparella è completamente aperta.",
    "hints.sequential_close.tilt_time_close":
      "Parti con la tapparella chiusa ma le lamelle aperte. Clicca su Fine quando le lamelle sono completamente chiuse.",
    "hints.sequential_close.tilt_time_open":
      "Parti con la tapparella e le lamelle chiuse. Clicca su Fine quando le lamelle sono aperte.",
    "hints.sequential_open.travel_time_close":
      "Parti con la tapparella completamente aperta e le lamelle chiuse. Clicca su Fine quando la tapparella è completamente chiusa, prima che le lamelle inizino ad aprirsi.",
    "hints.sequential_open.travel_time_open":
      "Parti con la tapparella chiusa e le lamelle chiuse. Clicca su Fine quando la tapparella è completamente aperta.",
    "hints.sequential_open.tilt_time_close":
      "Parti con la tapparella chiusa ma le lamelle aperte. Clicca su Fine quando le lamelle sono completamente chiuse.",
    "hints.sequential_open.tilt_time_open":
      "Parti con la tapparella e le lamelle chiuse. Clicca su Fine quando le lamelle sono completamente aperte.",
    "hints.dual_motor.travel_time_close":
      "Parti con la tapparella aperta e le lamelle nella posizione sicura. Clicca su Fine quando la tapparella è completamente chiusa.",
    "hints.dual_motor.travel_time_open":
      "Parti con la tapparella chiusa e le lamelle nella posizione sicura. Clicca su Fine quando la tapparella è completamente aperta.",
    "hints.dual_motor.tilt_time_close":
      "Parti con la tapparella chiusa e le lamelle aperte. Clicca su Fine quando le lamelle sono completamente chiuse.",
    "hints.dual_motor.tilt_time_open":
      "Parti con la tapparella e le lamelle entrambe chiuse. Clicca su Fine quando le lamelle sono completamente aperte.",
    "hints.inline.travel_time_close":
      "Parti con la tapparella e le lamelle entrambe completamente aperte. Clicca su Fine quando entrambe sono completamente chiuse.",
    "hints.inline.travel_time_open":
      "Parti con la tapparella e le lamelle entrambe completamente chiuse. Clicca su Fine quando entrambe sono completamente aperte.",
    "hints.inline.tilt_time_close":
      "Parti con le lamelle completamente aperte. Clicca su Fine quando le lamelle sono completamente chiuse.",
    "hints.inline.tilt_time_open":
      "Parti con le lamelle completamente chiuse. Clicca su Fine quando le lamelle sono completamente aperte.",
    "hints.none.travel_time_close": "Clicca su Fine quando la tapparella è completamente chiusa.",
    "hints.none.travel_time_open": "Clicca su Fine quando la tapparella è completamente aperta.",
    "hints.min_movement_time": "Clicca su Fine non appena noti che la tapparella si muove.",
  },
  nl: {
    header: "Configuratie van Cover Time Based",
    loading: "Laden...",
    saving: "Opslaan...",
    save_failed: "Opslaan mislukt — waarde teruggezet",
    confirm_cancel_calibration: "Er loopt een kalibratie. Deze annuleren en doorgaan?",
    create_new: "+ Nieuwe rolluikentiteit aanmaken",
    yaml_warning:
      "Deze entiteit gebruikt YAML-configuratie en kan niet vanuit deze kaart worden geconfigureerd. Migreer naar de gebruikersinterface: Instellingen → Apparaten en diensten → Helpers → Helper aanmaken → Cover Time Based.",
    load_failed: "Laden van de configuratie mislukt. Probeer het opnieuw.",
    admin_required:
      "Deze kaart vereist een beheerdersaccount. Log in als beheerder om rolluiken te configureren.",
    "tabs.device": "Apparaat",
    "tabs.calibration": "Kalibratie",
    "control_mode.label": "Besturingsmodus",
    "control_mode.wrapped": "Een bestaande rolluikentiteit inkapselen",
    "control_mode.switch": "Schakelaar (vergrendelend)",
    "control_mode.pulse": "Puls (momentaan)",
    "control_mode.toggle": "Omschakelen (zelfde knop)",
    "control_mode.toggle_opposite": "Omschakelen (tegenovergestelde knop)",
    "control_mode.single_button": "Enkele knop (cyclisch)",
    "control_mode.pulse_time": "Pulsduur",
    "entities.cover_entity": "Rolluikentiteit",
    "position_reporting.label": "Positierapportage",
    "position_reporting.reliable": "Betrouwbare positieterugkoppeling",
    "position_reporting.reliable_helper":
      "Het ingekapselde rolluik rapporteert een betrouwbare positie en bereikt zijn echte eindstanden voor open en gesloten. De standaard — de juiste keuze, tenzij de gevolgde positie afwijkt van waar het rolluik zich werkelijk bevindt.",
    "position_reporting.unreliable": "Positie onbetrouwbaar — volgen op tijd",
    "position_reporting.unreliable_helper":
      "Volg de positie uitsluitend op tijd en negeer de positie die het ingekapselde rolluik rapporteert. Schakel dit in als het onderliggende rolluik een onbetrouwbare positie rapporteert.",
    "position_reporting.no_endpoints": "Geen echte eindstanden — meldt open/gesloten bij stoppen",
    "position_reporting.no_endpoints_helper":
      "Voor rolluiken zonder positieterugkoppeling die open/gesloten melden wanneer de motor halverwege de beweging stopt in plaats van alleen bij de fysieke eindstanden. Een gemelde gesloten status stopt het volgen op de berekende positie in plaats van naar 0% te springen.",
    "position_reporting.command_echo": "Status weerspiegelt het laatste commando",
    "position_reporting.command_echo_helper":
      "Schakel dit in voor rolluiken (bijvoorbeeld sommige Tuya-rolluiken) waarvan de status open/gesloten/onbekend een echo van het commando is in plaats van een echte eindstand — ze rapporteren geen openings- of sluitingsovergang en geen positie. De status wordt behandeld als een commando openen/sluiten/stoppen en de positie wordt op tijd gevolgd.",
    "position_reporting.ignore_all": "Alle apparaatmeldingen negeren",
    "position_reporting.ignore_all_helper":
      "De status en positie van het apparaat zijn allemaal onbetrouwbaar. Negeer alles wat het meldt en volg de positie uitsluitend op basis van de open-/sluittijden. Home Assistant wordt de enige manier om het rolluik te bewegen — bediening via een wandschakelaar of afstandsbediening wordt niet gevolgd.",
    "position_reporting.docs_link": "Meer informatie",
    "entities.force_time_based_position": "Tijdgebaseerde positionering forceren",
    "entities.force_time_based_position_helper":
      "Standaard wordt het positiecommando rechtstreeks naar het ingekapselde rolluik gestuurd als dat het instellen van een positie ondersteunt. Schakel dit in om het in plaats daarvan aan te sturen met getimed openen/sluiten/stoppen, waarbij de eigen positieondersteuning wordt genegeerd.",
    "entities.invert": "Positie omkeren",
    "entities.invert_helper":
      "Keert de positie-as om: rapporteert 100 − de positie van het ingekapselde rolluik en verwisselt openen/sluiten. Gebruik dit voor rolluiken die omgekeerd lopen, bijvoorbeeld een zonnescherm waarvan de onderliggende entiteit open = uitgeschoven rapporteert. Alleen de positie-as; de kantellogica blijft ongewijzigd — bedoeld voor raambekleding met alleen een positie (zonneschermen/rolluiken), niet voor jaloezieën met verstelbare lamellen.",
    "entities.switch_entities": "Schakelaarentiteiten",
    "entities.open_switch": "Schakelaar voor openen",
    "entities.close_switch": "Schakelaar voor sluiten",
    "entities.stop_switch": "Schakelaar voor stoppen",
    "entities.switch_entities_pulse": "Schakelaar- / scriptentiteiten",
    "entities.open_switch_pulse": "Schakelaar of script voor openen",
    "entities.close_switch_pulse": "Schakelaar of script voor sluiten",
    "entities.stop_switch_pulse": "Schakelaar of script voor stoppen",
    "entities.button": "Knop",
    "tilt.label": "Kantelmodus",
    "tilt.none": "Niet ondersteund",
    "tilt.sequential_close": "Sluit en kantelt dan dicht",
    "tilt.sequential_open": "Sluit en kantelt dan open",
    "tilt.dual_motor": "Aparte kantelmotor",
    "tilt.inline": "Kantelt tijdens de beweging",
    "tilt_motor.label": "Kantelmotor",
    "tilt_motor.open_switch": "Schakelaar voor kanteling openen",
    "tilt_motor.close_switch": "Schakelaar voor kanteling sluiten",
    "tilt_motor.stop_switch": "Schakelaar voor kanteling stoppen",
    "tilt_motor.label_pulse": "Kantelmotor (schakelaar of script)",
    "tilt_motor.open_switch_pulse": "Schakelaar of script voor kanteling openen",
    "tilt_motor.close_switch_pulse": "Schakelaar of script voor kanteling sluiten",
    "tilt_motor.stop_switch_pulse": "Schakelaar of script voor kanteling stoppen",
    "tilt_motor.safe_position": "Veilige kantelpositie",
    "tilt_motor.safe_position_helper":
      "De kanteling gaat hierheen vóór de beweging (100 = volledig open)",
    "tilt_motor.max_allowed_position": "Maximaal toegestane kantelpositie (optioneel)",
    "tilt_motor.max_allowed_helper":
      "Kantelen is alleen toegestaan wanneer de rolluikpositie op of onder deze waarde ligt (0 = gesloten, 100 = open)",
    "tilt.close_includes_tilt": "Rolluik sluiten sluit ook de lamellen",
    "tilt.close_includes_tilt_helper":
      "Bij het sluiten kantelen de lamellen dicht aan het einde van de beweging",
    "assumed_state.label": "Aangenomen status",
    "assumed_state.helper":
      "Wanneer dit aanstaat, behandelt Home Assistant de positie als geschat en houdt het zowel de open- als de sluitknop actief. Schakel dit uit als je de tijdgebaseerde berekening vertrouwt en wilt dat de interface niet-beschikbare acties grijs maakt (bijvoorbeeld sluiten wanneer het rolluik al gesloten is).",
    "relay_reports_off.label": "Relais meldt zijn eigen UIT",
    "relay_reports_off.helper":
      "Laat dit aanstaan voor normale omschakelrelais, die zichzelf na de puls uitschakelen en dat ook melden. Schakel het uit voor hardwarematig aangestuurde pulsmodules (bijvoorbeeld de Aqara T2) die intern pulsen maar nooit melden wanneer ze uitschakelen, waardoor de schakelaarentiteit op aan blijft hangen. Als het uitstaat, stuurt de integratie per druk op de knop slechts één AAN-commando en nooit een UIT — zo is elke druk precies één schone activering, zonder dubbele commando's.",
    "send_endpoint_stop.label": "Stopsignaal bij de eindstanden versturen",
    "send_endpoint_stop.helper":
      "Stuur de stoppuls zodra je rolluik volledig open of gesloten is. Laat dit aanstaan voor besturingen die blijven doorlopen totdat ze een stop ontvangen (anders blijft het rolluik hangen en reageren de fysieke knoppen niet meer). Schakel het uit als je motor bij zijn eindstanden vanzelf stopt en een extra stop hem naar een vooraf ingestelde favoriete positie laat bewegen.",
    "force_endpoint_redrive.label": "Openen/sluiten altijd opnieuw versturen bij de eindstanden",
    "force_endpoint_redrive.helper":
      "Voor rolluiken zonder positieterugkoppeling die ook met een externe afstandsbediening bediend kunnen worden, waardoor Home Assistant ten onrechte kan denken dat ze al volledig open of gesloten zijn. Wanneer dit aanstaat, wordt een open- of sluitcommando altijd gedurende de volledige looptijd uitgevoerd, ook als Home Assistant denkt dat het rolluik daar al staat — zo bereikt het commando gegarandeerd de motor. Laat dit uitstaan voor rolluiken die hun eigen positie rapporteren.",
    "wait_for_relay_feedback.label": "Wacht op bevestiging van het relais voordat er gevolgd wordt",
    "wait_for_relay_feedback.helper":
      "Start de positietimer wanneer het relais meldt dat het is ingeschakeld, in plaats van op het moment dat het commando wordt verstuurd. Op een traag of koud Zigbee/Z-Wave-mesh kan het commando er seconden over doen om het relais te bereiken; zonder deze optie wordt die vertraging als beweging meegeteld en loopt de gevolgde positie voor op het rolluik. Laat dit uitstaan, tenzij de positie afwijkt bij rolluiken waarvan het relais traag reageert.",
    "recalibrate_before_position.label":
      "Volledig openen voordat naar een positie wordt bewogen (Beta)",
    "recalibrate_before_position.helper":
      "Voor rolluiken zonder positieterugkoppeling die ook door een afstandsbediening bewogen kunnen worden. Beweegt het rolluik vóór elk positiecommando eerst volledig open, zodat de beweging start vanaf een bekende positie in plaats van een afgedwaalde schatting. Verdubbelt daarmee ongeveer de looptijd van elke beweging, en bij kantelen tijdens de beweging of sequentieel kantelen beweegt het rolluik mee zodra je de lamellen verstelt.",
    "resync.label": "Hersynchroniseren",
    "resync.helper":
      "Vertel de integratie de werkelijke positie van het rolluik nadat het met de fysieke knop of een RF-afstandsbediening is bewogen. Dit verankert het volgen van de positie opnieuw en stopt de motor als Home Assistant die nog aanstuurt; hij wordt er nooit door gestart.",
    more_info: "Meer informatie",
    "timing.travel_attribute_header": "Loopattribuut",
    "timing.tilt_attribute_header": "Kantelattribuut",
    "timing.value_header": "Waarde",
    "timing.not_set": "Niet ingesteld",
    "timing.travel_time_close": "Looptijd (sluiten)",
    "timing.travel_time_open": "Looptijd (openen)",
    "timing.travel_startup_delay": "Opstartvertraging van de beweging",
    "timing.tilt_time_close": "Kanteltijd (sluiten)",
    "timing.tilt_time_open": "Kanteltijd (openen)",
    "timing.tilt_startup_delay": "Opstartvertraging van de kanteling",
    "timing.min_movement_time": "Minimale bewegingstijd",
    "timing.endpoint_runon_time": "Nalooptijd bij de eindstanden",
    "position.label": "Huidige positie",
    "position.helper": "Beweeg het rolluik naar een bekende eindstand en stel dan de positie in.",
    "position.unknown": "Onbekend",
    "position.open": "Volledig open",
    "position.closed": "Volledig gesloten",
    "position.closed_tilt_open": "Volledig gesloten, kanteling open",
    "position.closed_tilt_closed": "Volledig gesloten, kanteling dicht",
    "calibration.label": "Tijdkalibratie",
    "calibration.attribute_label": "Attribuut",
    "calibration.start": "Starten",
    "calibration.active": "Kalibratie actief",
    "calibration.step": "Stap {step}",
    "calibration.final_step": "Laatste stap",
    "calibration.cancel": "Annuleren",
    "calibration.finish": "Voltooien",
    "calibration.set_position_first": "Stel de positie in om de kalibratie te starten.",
    "controls.cover_label": "Rolluik",
    "controls.tilt_label": "Kanteling",
    "controls.open": "Openen",
    "controls.stop": "Stoppen",
    "controls.close": "Sluiten",
    "controls.tilt_open": "Kanteling openen",
    "controls.tilt_stop": "Kanteling stoppen",
    "controls.tilt_close": "Kanteling sluiten",
    "hints.sequential_close.travel_time_close":
      "Begin met het rolluik volledig open. Klik op Voltooien wanneer het rolluik volledig gesloten is, voordat de lamellen beginnen te kantelen.",
    "hints.sequential_close.travel_time_open":
      "Begin met het rolluik gesloten en de lamellen open. Klik op Voltooien wanneer het rolluik volledig open is.",
    "hints.sequential_close.tilt_time_close":
      "Begin met het rolluik gesloten maar de lamellen open. Klik op Voltooien wanneer de lamellen volledig gesloten zijn.",
    "hints.sequential_close.tilt_time_open":
      "Begin met het rolluik en de lamellen gesloten. Klik op Voltooien wanneer de lamellen open zijn.",
    "hints.sequential_open.travel_time_close":
      "Begin met het rolluik volledig open en de lamellen gesloten. Klik op Voltooien wanneer het rolluik volledig gesloten is, voordat de lamellen open beginnen te kantelen.",
    "hints.sequential_open.travel_time_open":
      "Begin met het rolluik gesloten en de lamellen gesloten. Klik op Voltooien wanneer het rolluik volledig open is.",
    "hints.sequential_open.tilt_time_close":
      "Begin met het rolluik gesloten maar de lamellen open. Klik op Voltooien wanneer de lamellen volledig gesloten zijn.",
    "hints.sequential_open.tilt_time_open":
      "Begin met het rolluik en de lamellen gesloten. Klik op Voltooien wanneer de lamellen volledig open zijn.",
    "hints.dual_motor.travel_time_close":
      "Begin met het rolluik open en de lamellen in de veilige positie. Klik op Voltooien wanneer het rolluik volledig gesloten is.",
    "hints.dual_motor.travel_time_open":
      "Begin met het rolluik gesloten en de lamellen in de veilige positie. Klik op Voltooien wanneer het rolluik volledig open is.",
    "hints.dual_motor.tilt_time_close":
      "Begin met het rolluik gesloten en de lamellen open. Klik op Voltooien wanneer de lamellen volledig gesloten zijn.",
    "hints.dual_motor.tilt_time_open":
      "Begin met zowel het rolluik als de lamellen gesloten. Klik op Voltooien wanneer de lamellen volledig open zijn.",
    "hints.inline.travel_time_close":
      "Begin met zowel het rolluik als de lamellen volledig open. Klik op Voltooien wanneer beide volledig gesloten zijn.",
    "hints.inline.travel_time_open":
      "Begin met zowel het rolluik als de lamellen volledig gesloten. Klik op Voltooien wanneer beide volledig open zijn.",
    "hints.inline.tilt_time_close":
      "Begin met de lamellen volledig open. Klik op Voltooien wanneer de lamellen volledig gesloten zijn.",
    "hints.inline.tilt_time_open":
      "Begin met de lamellen volledig gesloten. Klik op Voltooien wanneer de lamellen volledig open zijn.",
    "hints.none.travel_time_close": "Klik op Voltooien wanneer het rolluik volledig gesloten is.",
    "hints.none.travel_time_open": "Klik op Voltooien wanneer het rolluik volledig open is.",
    "hints.min_movement_time": "Klik op Voltooien zodra je het rolluik ziet bewegen.",
  },
  fr: {
    header: "Configuration de Cover Time Based",
    loading: "Chargement...",
    saving: "Enregistrement...",
    save_failed: "Échec de l'enregistrement — valeur rétablie",
    confirm_cancel_calibration: "Un étalonnage est en cours. L'annuler et continuer\u00a0?",
    create_new: "+ Créer une nouvelle entité de volet",
    yaml_warning:
      "Cette entité utilise une configuration YAML et ne peut pas être configurée depuis cette carte. Veuillez migrer vers l'interface utilisateur\u00a0: Paramètres → Appareils et services → Entrées → Créer une entrée → Cover Time Based.",
    load_failed: "Échec du chargement de la configuration. Veuillez réessayer.",
    admin_required:
      "Cette carte nécessite un compte administrateur. Veuillez vous connecter en tant qu'administrateur pour configurer les volets.",
    "tabs.device": "Appareil",
    "tabs.calibration": "Étalonnage",
    "control_mode.label": "Mode de commande",
    "control_mode.wrapped": "Encapsuler une entité de volet existante",
    "control_mode.switch": "Interrupteur (maintenu)",
    "control_mode.pulse": "Impulsion (momentanée)",
    "control_mode.toggle": "Bascule (même bouton)",
    "control_mode.toggle_opposite": "Bascule (bouton opposé)",
    "control_mode.single_button": "Bouton unique (cyclique)",
    "control_mode.pulse_time": "Durée de l'impulsion",
    "entities.cover_entity": "Entité de volet",
    "position_reporting.label": "Rapport de position",
    "position_reporting.reliable": "Retour de position fiable",
    "position_reporting.reliable_helper":
      "Le volet encapsulé rapporte une position fiable et atteint ses véritables fins de course ouvert/fermé. Option par défaut — le bon choix, sauf si la position suivie dérive par rapport à la position réelle du volet.",
    "position_reporting.unreliable": "Position peu fiable — suivre d'après le temps",
    "position_reporting.unreliable_helper":
      "Suivre la position uniquement d'après le temps et ignorer la position rapportée par le volet encapsulé. Activez cette option si le volet sous-jacent rapporte une position peu fiable.",
    "position_reporting.no_endpoints":
      "Pas de véritables fins de course — rapporte ouvert/fermé à l'arrêt",
    "position_reporting.no_endpoints_helper":
      "Pour les volets sans retour de position qui rapportent ouvert/fermé lorsque le moteur s'arrête en pleine course plutôt qu'uniquement aux fins de course physiques. Un état fermé rapporté arrête le suivi à la position calculée au lieu de la ramener à 0%.",
    "position_reporting.command_echo": "L'état reflète la dernière commande",
    "position_reporting.command_echo_helper":
      "Activez cette option pour les volets (par exemple certains volets Tuya) dont l'état ouvert/fermé/inconnu est un écho de la commande plutôt qu'une véritable fin de course — ils ne rapportent ni transition d'ouverture/fermeture, ni position. L'état est traité comme une commande d'ouverture/fermeture/arrêt et la position est suivie d'après le temps.",
    "position_reporting.ignore_all": "Ignorer tous les rapports de l'appareil",
    "position_reporting.ignore_all_helper":
      "L'état et la position de l'appareil ne sont pas fiables. Ignorez tout ce qu'il rapporte et suivez la position uniquement d'après les durées d'ouverture/fermeture. Home Assistant devient le seul moyen de bouger le volet — une commande par interrupteur mural ou télécommande n'est pas suivie.",
    "position_reporting.docs_link": "En savoir plus",
    "entities.force_time_based_position": "Forcer le positionnement temporisé",
    "entities.force_time_based_position_helper":
      "Par défaut, si le volet encapsulé prend en charge le réglage de la position, la commande de position lui est envoyée directement. Activez cette option pour le piloter à la place par ouverture/fermeture/arrêt temporisés, en ignorant sa prise en charge native du réglage de position.",
    "entities.invert": "Inverser la position",
    "entities.invert_helper":
      "Inverse l'axe de position\u00a0: rapporte 100 − la position du volet encapsulé et permute ouverture/fermeture. À utiliser pour les volets qui fonctionnent à l'envers, par exemple un store banne dont l'entité sous-jacente rapporte ouvert = déployé. Concerne uniquement l'axe de position\u00a0; la logique d'inclinaison est inchangée — prévu pour les ouvertures qui ne gèrent que la position (stores bannes/volets roulants), pas pour les stores vénitiens à lames orientables.",
    "entities.switch_entities": "Entités d'interrupteur",
    "entities.open_switch": "Interrupteur d'ouverture",
    "entities.close_switch": "Interrupteur de fermeture",
    "entities.stop_switch": "Interrupteur d'arrêt",
    "entities.switch_entities_pulse": "Entités d'interrupteur / de script",
    "entities.open_switch_pulse": "Interrupteur ou script d'ouverture",
    "entities.close_switch_pulse": "Interrupteur ou script de fermeture",
    "entities.stop_switch_pulse": "Interrupteur ou script d'arrêt",
    "entities.button": "Bouton",
    "tilt.label": "Mode d'inclinaison",
    "tilt.none": "Non pris en charge",
    "tilt.sequential_close": "Ferme, puis ferme l'inclinaison",
    "tilt.sequential_open": "Ferme, puis ouvre l'inclinaison",
    "tilt.dual_motor": "Moteur d'inclinaison séparé",
    "tilt.inline": "Incline pendant la course",
    "tilt_motor.label": "Moteur d'inclinaison",
    "tilt_motor.open_switch": "Interrupteur d'ouverture de l'inclinaison",
    "tilt_motor.close_switch": "Interrupteur de fermeture de l'inclinaison",
    "tilt_motor.stop_switch": "Interrupteur d'arrêt de l'inclinaison",
    "tilt_motor.label_pulse": "Moteur d'inclinaison (interrupteur ou script)",
    "tilt_motor.open_switch_pulse": "Interrupteur ou script d'ouverture de l'inclinaison",
    "tilt_motor.close_switch_pulse": "Interrupteur ou script de fermeture de l'inclinaison",
    "tilt_motor.stop_switch_pulse": "Interrupteur ou script d'arrêt de l'inclinaison",
    "tilt_motor.safe_position": "Position d'inclinaison de sécurité",
    "tilt_motor.safe_position_helper":
      "L'inclinaison se place ici avant la course (100 = complètement ouverte)",
    "tilt_motor.max_allowed_position": "Position d'inclinaison maximale autorisée (facultatif)",
    "tilt_motor.max_allowed_helper":
      "L'inclinaison n'est autorisée que lorsque la position du volet est égale ou inférieure à cette valeur (0 = fermé, 100 = ouvert)",
    "tilt.close_includes_tilt": "Fermer le volet ferme aussi les lames",
    "tilt.close_includes_tilt_helper":
      "À la fermeture, les lames s'inclinent en position fermée en fin de course",
    "assumed_state.label": "État supposé",
    "assumed_state.helper":
      "Lorsque cette option est activée, Home Assistant considère la position comme estimée et garde actives les commandes d'ouverture et de fermeture. Désactivez-la si vous faites confiance au calcul temporisé et souhaitez que l'interface grise les actions indisponibles (par exemple fermer alors que le volet est déjà fermé).",
    "relay_reports_off.label": "Le relais rapporte sa propre désactivation",
    "relay_reports_off.helper":
      "Laissez cette option activée pour les relais à bascule ordinaires, qui se désactivent d'eux-mêmes après l'impulsion et le rapportent. Désactivez-la pour les modules à impulsion gérés par le matériel (par exemple l'Aqara T2), qui génèrent l'impulsion en interne mais ne rapportent jamais leur désactivation, laissant l'entité d'interrupteur bloquée à l'état activé. Une fois cette option désactivée, l'intégration n'envoie qu'une seule commande ACTIVER par appui, et jamais de commande DÉSACTIVER — chaque appui correspond ainsi exactement à une activation propre, sans commande dupliquée.",
    "send_endpoint_stop.label": "Envoyer un signal d'arrêt en fin de course",
    "send_endpoint_stop.helper":
      "Lorsque votre volet atteint l'ouverture ou la fermeture complète, envoyez l'impulsion d'arrêt. Gardez cette option activée pour les contrôleurs qui continuent de fonctionner tant qu'ils n'ont pas reçu d'arrêt (sans quoi le volet se bloque et les boutons physiques ne répondent plus). Désactivez-la si votre moteur s'arrête de lui-même à ses butées et qu'un arrêt supplémentaire le fait aller à une position prédéfinie/favorite.",
    "force_endpoint_redrive.label": "Toujours renvoyer ouvrir/fermer en fin de course",
    "force_endpoint_redrive.helper":
      "Pour les volets sans retour de position qui peuvent aussi être actionnés par une télécommande externe, si bien que Home Assistant peut croire à tort qu'ils sont déjà complètement ouverts ou fermés. Lorsque cette option est activée, une commande d'ouverture ou de fermeture est toujours exécutée pendant la totalité du temps de course, même si Home Assistant pense que le volet y est déjà — ce qui garantit que la commande atteint le moteur. Laissez-la désactivée pour les volets qui rapportent leur propre position.",
    "wait_for_relay_feedback.label": "Attendre la confirmation du relais avant le suivi",
    "wait_for_relay_feedback.helper":
      "Démarre le minuteur de position lorsque le relais signale qu'il s'est activé, plutôt qu'au moment où la commande est envoyée. Sur un réseau maillé Zigbee/Z-Wave lent ou froid, la commande peut mettre plusieurs secondes à atteindre le relais ; sans cette option, ce délai est compté comme de la course et la position suivie devance le volet. Laissez cette option désactivée, sauf si la position dérive sur des volets dont le relais répond lentement.",
    "recalibrate_before_position.label": "Ouvrir complètement avant d'aller à une position (Bêta)",
    "recalibrate_before_position.helper":
      "Pour les volets sans retour de position qu'une télécommande peut aussi actionner. Ouvre complètement le volet avant chaque commande de position, afin que le mouvement parte d'une position connue plutôt que d'une estimation partie à la dérive. Cela double à peu près la course de chaque mouvement et, avec une inclinaison pendant la course ou une inclinaison séquentielle, le volet bouge lorsque vous réglez les lames.",
    "resync.label": "Resynchroniser",
    "resync.helper":
      "Indiquez à l'intégration la position réelle du volet après qu'il a été actionné par le bouton physique ou une télécommande RF. Cela réancre le suivi de position et arrête le moteur si Home Assistant le pilote encore ; il n'est jamais démarré.",
    more_info: "Plus d'informations",
    "timing.travel_attribute_header": "Attribut de course",
    "timing.tilt_attribute_header": "Attribut d'inclinaison",
    "timing.value_header": "Valeur",
    "timing.not_set": "Non défini",
    "timing.travel_time_close": "Temps de course (fermeture)",
    "timing.travel_time_open": "Temps de course (ouverture)",
    "timing.travel_startup_delay": "Délai de démarrage de la course",
    "timing.tilt_time_close": "Temps d'inclinaison (fermeture)",
    "timing.tilt_time_open": "Temps d'inclinaison (ouverture)",
    "timing.tilt_startup_delay": "Délai de démarrage de l'inclinaison",
    "timing.min_movement_time": "Temps de mouvement minimal",
    "timing.endpoint_runon_time": "Temps de prolongation en fin de course",
    "position.label": "Position actuelle",
    "position.helper": "Amenez le volet à une fin de course connue, puis définissez la position.",
    "position.unknown": "Inconnu",
    "position.open": "Complètement ouvert",
    "position.closed": "Complètement fermé",
    "position.closed_tilt_open": "Complètement fermé, inclinaison ouverte",
    "position.closed_tilt_closed": "Complètement fermé, inclinaison fermée",
    "calibration.label": "Étalonnage des temporisations",
    "calibration.attribute_label": "Attribut",
    "calibration.start": "Démarrer",
    "calibration.active": "Étalonnage en cours",
    "calibration.step": "Étape {step}",
    "calibration.final_step": "Dernière étape",
    "calibration.cancel": "Annuler",
    "calibration.finish": "Terminer",
    "calibration.set_position_first": "Définissez la position pour démarrer l'étalonnage.",
    "controls.cover_label": "Volet",
    "controls.tilt_label": "Inclinaison",
    "controls.open": "Ouvrir",
    "controls.stop": "Arrêter",
    "controls.close": "Fermer",
    "controls.tilt_open": "Ouvrir l'inclinaison",
    "controls.tilt_stop": "Arrêter l'inclinaison",
    "controls.tilt_close": "Fermer l'inclinaison",
    "hints.sequential_close.travel_time_close":
      "Commencez avec le volet complètement ouvert. Cliquez sur Terminer lorsque le volet est complètement fermé, avant que les lames ne commencent à s'incliner.",
    "hints.sequential_close.travel_time_open":
      "Commencez avec le volet fermé et les lames ouvertes. Cliquez sur Terminer lorsque le volet est complètement ouvert.",
    "hints.sequential_close.tilt_time_close":
      "Commencez avec le volet fermé mais les lames ouvertes. Cliquez sur Terminer lorsque les lames sont complètement fermées.",
    "hints.sequential_close.tilt_time_open":
      "Commencez avec le volet et les lames fermés. Cliquez sur Terminer lorsque les lames sont ouvertes.",
    "hints.sequential_open.travel_time_close":
      "Commencez avec le volet complètement ouvert et les lames fermées. Cliquez sur Terminer lorsque le volet est complètement fermé, avant que les lames ne commencent à s'ouvrir.",
    "hints.sequential_open.travel_time_open":
      "Commencez avec le volet fermé et les lames fermées. Cliquez sur Terminer lorsque le volet est complètement ouvert.",
    "hints.sequential_open.tilt_time_close":
      "Commencez avec le volet fermé mais les lames ouvertes. Cliquez sur Terminer lorsque les lames sont complètement fermées.",
    "hints.sequential_open.tilt_time_open":
      "Commencez avec le volet et les lames fermés. Cliquez sur Terminer lorsque les lames sont complètement ouvertes.",
    "hints.dual_motor.travel_time_close":
      "Commencez avec le volet ouvert et les lames en position de sécurité. Cliquez sur Terminer lorsque le volet est complètement fermé.",
    "hints.dual_motor.travel_time_open":
      "Commencez avec le volet fermé et les lames en position de sécurité. Cliquez sur Terminer lorsque le volet est complètement ouvert.",
    "hints.dual_motor.tilt_time_close":
      "Commencez avec le volet fermé et les lames ouvertes. Cliquez sur Terminer lorsque les lames sont complètement fermées.",
    "hints.dual_motor.tilt_time_open":
      "Commencez avec le volet et les lames fermés. Cliquez sur Terminer lorsque les lames sont complètement ouvertes.",
    "hints.inline.travel_time_close":
      "Commencez avec le volet et les lames complètement ouverts. Cliquez sur Terminer lorsque les deux sont complètement fermés.",
    "hints.inline.travel_time_open":
      "Commencez avec le volet et les lames complètement fermés. Cliquez sur Terminer lorsque les deux sont complètement ouverts.",
    "hints.inline.tilt_time_close":
      "Commencez avec les lames complètement ouvertes. Cliquez sur Terminer lorsque les lames sont complètement fermées.",
    "hints.inline.tilt_time_open":
      "Commencez avec les lames complètement fermées. Cliquez sur Terminer lorsque les lames sont complètement ouvertes.",
    "hints.none.travel_time_close": "Cliquez sur Terminer lorsque le volet est complètement fermé.",
    "hints.none.travel_time_open": "Cliquez sur Terminer lorsque le volet est complètement ouvert.",
    "hints.min_movement_time": "Cliquez sur Terminer dès que vous voyez le volet bouger.",
  },
  es: {
    header: "Configuración de Cover Time Based",
    loading: "Cargando...",
    saving: "Guardando...",
    save_failed: "Error al guardar — valor restaurado",
    confirm_cancel_calibration: "Hay una calibración en curso. ¿Cancelarla y continuar?",
    create_new: "+ Crear una nueva entidad de persiana",
    yaml_warning:
      "Esta entidad usa configuración YAML y no se puede configurar desde esta tarjeta. Migra a la interfaz de usuario: Configuración → Dispositivos y servicios → Ayudantes → Crear ayudante → Cover Time Based.",
    load_failed: "Error al cargar la configuración. Inténtalo de nuevo.",
    admin_required:
      "Esta tarjeta necesita una cuenta de administrador. Inicia sesión como administrador para configurar persianas.",
    "tabs.device": "Dispositivo",
    "tabs.calibration": "Calibración",
    "control_mode.label": "Modo de control",
    "control_mode.wrapped": "Envolver una entidad de persiana existente",
    "control_mode.switch": "Interruptor (mantenido)",
    "control_mode.pulse": "Impulso (momentáneo)",
    "control_mode.toggle": "Alternar (mismo botón)",
    "control_mode.toggle_opposite": "Alternar (botón opuesto)",
    "control_mode.single_button": "Botón único (cíclico)",
    "control_mode.pulse_time": "Duración del impulso",
    "entities.cover_entity": "Entidad de persiana",
    "position_reporting.label": "Informe de posición",
    "position_reporting.reliable": "Realimentación de posición fiable",
    "position_reporting.reliable_helper":
      "La persiana envuelta informa de una posición fiable y alcanza sus finales de carrera reales de apertura y cierre. La opción predeterminada — la elección correcta a menos que la posición rastreada se desvíe de la posición real de la persiana.",
    "position_reporting.unreliable": "Posición poco fiable — seguir por tiempo",
    "position_reporting.unreliable_helper":
      "Seguir la posición solo por tiempo e ignorar la posición que indica la persiana envuelta. Activa esta opción si la persiana subyacente informa de una posición poco fiable.",
    "position_reporting.no_endpoints":
      "Sin finales de carrera reales — informa de abierto/cerrado al detenerse",
    "position_reporting.no_endpoints_helper":
      "Para persianas sin realimentación de posición que informan de abierto/cerrado cuando el motor se detiene a mitad del recorrido en lugar de solo en los finales de carrera físicos. Un estado cerrado informado detiene el seguimiento en la posición calculada en lugar de saltar a 0%.",
    "position_reporting.command_echo": "El estado refleja el último comando",
    "position_reporting.command_echo_helper":
      "Actívalo para persianas (por ejemplo, algunas persianas Tuya) cuyo estado abierto/cerrado/desconocido es un eco del comando en lugar de una posición final real: no informan ninguna transición de apertura o cierre ni ninguna posición. El estado se trata como un comando de abrir/cerrar/detener y la posición se sigue por tiempo.",
    "position_reporting.ignore_all": "Ignorar todos los informes del dispositivo",
    "position_reporting.ignore_all_helper":
      "El estado y la posición del dispositivo no son fiables. Ignora todo lo que informa y sigue la posición únicamente por los tiempos de apertura/cierre. Home Assistant se convierte en la única forma de mover la persiana; su manejo mediante un interruptor de pared o mando a distancia no se rastrea.",
    "position_reporting.docs_link": "Más información",
    "entities.force_time_based_position": "Forzar el posicionamiento por tiempo",
    "entities.force_time_based_position_helper":
      "De forma predeterminada, si la persiana envuelta admite establecer la posición, el comando de posición se le envía directamente. Activa esta opción para accionarla en su lugar con apertura/cierre/parada temporizados, ignorando su compatibilidad nativa con el establecimiento de posición.",
    "entities.invert": "Invertir la posición",
    "entities.invert_helper":
      "Invierte el eje de posición: informa de 100 − la posición de la persiana envuelta e intercambia apertura y cierre. Úsalo para persianas que funcionan al revés, por ejemplo un toldo cuya entidad subyacente indica abierto = extendido. Solo afecta al eje de posición; la lógica de inclinación no cambia: está pensado para persianas y toldos que solo tienen posición, no para venecianas con lamas orientables.",
    "entities.switch_entities": "Entidades de interruptor",
    "entities.open_switch": "Interruptor de apertura",
    "entities.close_switch": "Interruptor de cierre",
    "entities.stop_switch": "Interruptor de parada",
    "entities.switch_entities_pulse": "Entidades de interruptor / script",
    "entities.open_switch_pulse": "Interruptor o script de apertura",
    "entities.close_switch_pulse": "Interruptor o script de cierre",
    "entities.stop_switch_pulse": "Interruptor o script de parada",
    "entities.button": "Botón",
    "tilt.label": "Modo de inclinación",
    "tilt.none": "No compatible",
    "tilt.sequential_close": "Cierra y luego inclina a cerrado",
    "tilt.sequential_open": "Cierra y luego inclina a abierto",
    "tilt.dual_motor": "Motor de inclinación independiente",
    "tilt.inline": "Inclina durante el recorrido",
    "tilt_motor.label": "Motor de inclinación",
    "tilt_motor.open_switch": "Interruptor de apertura de la inclinación",
    "tilt_motor.close_switch": "Interruptor de cierre de la inclinación",
    "tilt_motor.stop_switch": "Interruptor de parada de la inclinación",
    "tilt_motor.label_pulse": "Motor de inclinación (interruptor o script)",
    "tilt_motor.open_switch_pulse": "Interruptor o script de apertura de la inclinación",
    "tilt_motor.close_switch_pulse": "Interruptor o script de cierre de la inclinación",
    "tilt_motor.stop_switch_pulse": "Interruptor o script de parada de la inclinación",
    "tilt_motor.safe_position": "Posición de inclinación segura",
    "tilt_motor.safe_position_helper":
      "La inclinación se mueve aquí antes del recorrido (100 = totalmente abierta)",
    "tilt_motor.max_allowed_position": "Posición máxima de inclinación permitida (opcional)",
    "tilt_motor.max_allowed_helper":
      "La inclinación solo se permite cuando la posición de la persiana es igual o inferior a este valor (0 = cerrada, 100 = abierta)",
    "tilt.close_includes_tilt": "Cerrar la persiana también cierra las lamas",
    "tilt.close_includes_tilt_helper":
      "Al cerrar, las lamas se inclinan a cerrado al final del recorrido",
    "assumed_state.label": "Estado supuesto",
    "assumed_state.helper":
      "Cuando está activado, Home Assistant trata la posición como estimada y mantiene activos los controles de apertura y cierre. Desactívalo si confías en el cálculo por tiempo y quieres que la interfaz atenúe las acciones no disponibles (por ejemplo, cerrar cuando ya está cerrada).",
    "relay_reports_off.label": "El relé informa de su propio apagado",
    "relay_reports_off.helper":
      "Déjalo activado para los relés de conmutación normales, que se desconectan solos después del impulso y lo informan. Desactívalo para los módulos de impulso gestionados por hardware (por ejemplo, el Aqara T2), que generan el impulso internamente pero nunca informan cuando se desconectan, y dejan la entidad de interruptor bloqueada en encendido. Con la opción desactivada, la integración solo envía un único comando de ENCENDIDO por pulsación y nunca uno de APAGADO, de modo que cada pulsación es exactamente una activación limpia, sin comandos duplicados.",
    "send_endpoint_stop.label": "Enviar señal de parada en los finales de carrera",
    "send_endpoint_stop.helper":
      "Cuando tu persiana llegue a la posición totalmente abierta o cerrada, envía el impulso de parada. Mantén esta opción activada para los controladores que siguen funcionando hasta que reciben una parada (si no, la persiana se queda bloqueada y los botones físicos dejan de responder). Desactívala si tu motor se detiene por sí solo en sus finales de carrera y una parada adicional hace que se mueva a una posición predefinida o favorita.",
    "force_endpoint_redrive.label": "Reenviar siempre abrir/cerrar en los finales de carrera",
    "force_endpoint_redrive.helper":
      "Para persianas sin realimentación de posición que también se pueden mover con un mando a distancia externo, de modo que Home Assistant puede creer erróneamente que ya están totalmente abiertas o cerradas. Cuando está activado, un comando de apertura o cierre siempre se ejecuta durante todo el tiempo de recorrido aunque Home Assistant crea que la persiana ya está ahí, lo que garantiza que el comando llega al motor. Déjalo desactivado para las persianas que informan de su propia posición.",
    "wait_for_relay_feedback.label": "Esperar la confirmación del relé antes de rastrear",
    "wait_for_relay_feedback.helper":
      "Inicia el temporizador de posición cuando el relé informa de que se ha encendido, en lugar del momento en que se envía el comando. En una red mallada Zigbee/Z-Wave lenta o fría, el comando puede tardar segundos en llegar al relé; sin esta opción, ese retardo se cuenta como recorrido y la posición rastreada se adelanta a la persiana. Déjalo desactivado, a menos que la posición se desvíe en persianas cuyo relé responde con lentitud.",
    "recalibrate_before_position.label": "Abrir totalmente antes de mover a una posición (Beta)",
    "recalibrate_before_position.helper":
      "Para persianas sin realimentación de posición que un mando a distancia también puede mover. Abre la persiana por completo antes de cada comando de posición, para que el movimiento parta de una posición conocida en lugar de una estimación desviada. Duplica aproximadamente el recorrido de cada movimiento y, con la inclinación durante el recorrido o la inclinación secuencial, mueve la persiana cuando ajustas las lamas.",
    "resync.label": "Resincronizar",
    "resync.helper":
      "Indica a la integración la posición real de la persiana después de haberla movido con el botón físico o un mando a distancia RF. Esto reancla el seguimiento de la posición y detiene el motor si Home Assistant todavía lo está accionando; nunca lo pone en marcha.",
    more_info: "Más información",
    "timing.travel_attribute_header": "Atributo de recorrido",
    "timing.tilt_attribute_header": "Atributo de inclinación",
    "timing.value_header": "Valor",
    "timing.not_set": "Sin definir",
    "timing.travel_time_close": "Tiempo de recorrido (cierre)",
    "timing.travel_time_open": "Tiempo de recorrido (apertura)",
    "timing.travel_startup_delay": "Retardo de arranque del recorrido",
    "timing.tilt_time_close": "Tiempo de inclinación (cierre)",
    "timing.tilt_time_open": "Tiempo de inclinación (apertura)",
    "timing.tilt_startup_delay": "Retardo de arranque de la inclinación",
    "timing.min_movement_time": "Tiempo mínimo de movimiento",
    "timing.endpoint_runon_time": "Tiempo de prolongación en los finales de carrera",
    "position.label": "Posición actual",
    "position.helper":
      "Mueve la persiana a un final de carrera conocido y luego establece la posición.",
    "position.unknown": "Desconocida",
    "position.open": "Totalmente abierta",
    "position.closed": "Totalmente cerrada",
    "position.closed_tilt_open": "Totalmente cerrada, inclinación abierta",
    "position.closed_tilt_closed": "Totalmente cerrada, inclinación cerrada",
    "calibration.label": "Calibración de tiempos",
    "calibration.attribute_label": "Atributo",
    "calibration.start": "Iniciar",
    "calibration.active": "Calibración activa",
    "calibration.step": "Paso {step}",
    "calibration.final_step": "Último paso",
    "calibration.cancel": "Cancelar",
    "calibration.finish": "Terminar",
    "calibration.set_position_first": "Establece la posición para iniciar la calibración.",
    "controls.cover_label": "Persiana",
    "controls.tilt_label": "Inclinación",
    "controls.open": "Abrir",
    "controls.stop": "Detener",
    "controls.close": "Cerrar",
    "controls.tilt_open": "Abrir la inclinación",
    "controls.tilt_stop": "Detener la inclinación",
    "controls.tilt_close": "Cerrar la inclinación",
    "hints.sequential_close.travel_time_close":
      "Empieza con la persiana totalmente abierta. Haz clic en Terminar cuando la persiana esté totalmente cerrada, antes de que las lamas empiecen a inclinarse.",
    "hints.sequential_close.travel_time_open":
      "Empieza con la persiana cerrada y las lamas abiertas. Haz clic en Terminar cuando la persiana esté totalmente abierta.",
    "hints.sequential_close.tilt_time_close":
      "Empieza con la persiana cerrada pero las lamas abiertas. Haz clic en Terminar cuando las lamas estén totalmente cerradas.",
    "hints.sequential_close.tilt_time_open":
      "Empieza con la persiana y las lamas cerradas. Haz clic en Terminar cuando las lamas estén abiertas.",
    "hints.sequential_open.travel_time_close":
      "Empieza con la persiana totalmente abierta y las lamas cerradas. Haz clic en Terminar cuando la persiana esté totalmente cerrada, antes de que las lamas empiecen a inclinarse hacia abierto.",
    "hints.sequential_open.travel_time_open":
      "Empieza con la persiana cerrada y las lamas cerradas. Haz clic en Terminar cuando la persiana esté totalmente abierta.",
    "hints.sequential_open.tilt_time_close":
      "Empieza con la persiana cerrada pero las lamas abiertas. Haz clic en Terminar cuando las lamas estén totalmente cerradas.",
    "hints.sequential_open.tilt_time_open":
      "Empieza con la persiana y las lamas cerradas. Haz clic en Terminar cuando las lamas estén totalmente abiertas.",
    "hints.dual_motor.travel_time_close":
      "Empieza con la persiana abierta y las lamas en la posición segura. Haz clic en Terminar cuando la persiana esté totalmente cerrada.",
    "hints.dual_motor.travel_time_open":
      "Empieza con la persiana cerrada y las lamas en la posición segura. Haz clic en Terminar cuando la persiana esté totalmente abierta.",
    "hints.dual_motor.tilt_time_close":
      "Empieza con la persiana cerrada y las lamas abiertas. Haz clic en Terminar cuando las lamas estén totalmente cerradas.",
    "hints.dual_motor.tilt_time_open":
      "Empieza con la persiana y las lamas cerradas. Haz clic en Terminar cuando las lamas estén totalmente abiertas.",
    "hints.inline.travel_time_close":
      "Empieza con la persiana y las lamas totalmente abiertas. Haz clic en Terminar cuando ambas estén totalmente cerradas.",
    "hints.inline.travel_time_open":
      "Empieza con la persiana y las lamas totalmente cerradas. Haz clic en Terminar cuando ambas estén totalmente abiertas.",
    "hints.inline.tilt_time_close":
      "Empieza con las lamas totalmente abiertas. Haz clic en Terminar cuando las lamas estén totalmente cerradas.",
    "hints.inline.tilt_time_open":
      "Empieza con las lamas totalmente cerradas. Haz clic en Terminar cuando las lamas estén totalmente abiertas.",
    "hints.none.travel_time_close":
      "Haz clic en Terminar cuando la persiana esté totalmente cerrada.",
    "hints.none.travel_time_open":
      "Haz clic en Terminar cuando la persiana esté totalmente abierta.",
    "hints.min_movement_time": "Haz clic en Terminar en cuanto notes que la persiana se mueve.",
  },
  ca: {
    header: "Configuració de Cover Time Based",
    loading: "Carregant...",
    saving: "Desant...",
    save_failed: "Error en desar — valor revertit",
    confirm_cancel_calibration: "Hi ha una calibració en curs. Vols cancel·lar-la i continuar?",
    create_new: "+ Crea una nova entitat de persiana",
    yaml_warning:
      "Aquesta entitat utilitza configuració YAML i no es pot configurar des d'aquesta targeta. Migra a la interfície d'usuari: Configuració → Dispositius i serveis → Ajudants → Crea ajudant → Cover Time Based.",
    load_failed: "No s'ha pogut carregar la configuració. Torna-ho a provar.",
    admin_required:
      "Aquesta targeta necessita un compte d'administrador. Inicia la sessió com a administrador per configurar persianes.",
    "tabs.device": "Dispositiu",
    "tabs.calibration": "Calibració",
    "control_mode.label": "Mode de control",
    "control_mode.wrapped": "Embolcalla una entitat de persiana existent",
    "control_mode.switch": "Interruptor (mantingut)",
    "control_mode.pulse": "Impuls (momentani)",
    "control_mode.toggle": "Commutació (mateix botó)",
    "control_mode.toggle_opposite": "Commutació (botó oposat)",
    "control_mode.single_button": "Botó únic (cíclic)",
    "control_mode.pulse_time": "Durada de l'impuls",
    "entities.cover_entity": "Entitat de persiana",
    "position_reporting.label": "Informe de posició",
    "position_reporting.reliable": "Realimentació de posició fiable",
    "position_reporting.reliable_helper":
      "La persiana embolcallada informa d'una posició fiable i arriba als seus finals de cursa reals d'obertura i tancament. L'opció per defecte — la tria correcta tret que la posició seguida es desviï d'on és realment la persiana.",
    "position_reporting.unreliable": "Posició poc fiable — segueix per temps",
    "position_reporting.unreliable_helper":
      "Fes el seguiment de la posició només per temps i ignora la posició que indica la persiana embolcallada. Activa aquesta opció si la persiana subjacent informa d'una posició poc fiable.",
    "position_reporting.no_endpoints":
      "Sense finals de cursa reals — informa d'obert/tancat en aturar-se",
    "position_reporting.no_endpoints_helper":
      "Per a persianes sense realimentació de posició que informen d'obert/tancat quan el motor s'atura a mig recorregut en lloc de fer-ho només als finals de cursa físics. Quan s'informa d'un estat de tancat, el seguiment s'atura a la posició calculada en lloc de saltar a 0%.",
    "position_reporting.command_echo": "L'estat reflecteix l'última ordre",
    "position_reporting.command_echo_helper":
      "Activa-ho per a persianes (per exemple, algunes persianes Tuya) l'estat obert/tancat/desconegut de les quals és un eco de l'ordre en lloc d'un final de cursa real: no informen cap transició d'obertura o tancament ni cap posició. L'estat es tracta com una ordre d'obrir/tancar/aturar i el seguiment de la posició es fa per temps.",
    "position_reporting.ignore_all": "Ignora tots els informes del dispositiu",
    "position_reporting.ignore_all_helper":
      "L'estat i la posició del dispositiu no són fiables. Ignora tot el que informa i fes el seguiment de la posició només pels temps d'obertura/tancament. El Home Assistant esdevé l'única manera de moure la persiana; el maneig mitjançant un interruptor de paret o comandament a distància no es fa el seguiment.",
    "position_reporting.docs_link": "Més informació",
    "entities.force_time_based_position": "Força el posicionament per temps",
    "entities.force_time_based_position_helper":
      "Per defecte, si la persiana embolcallada admet establir la posició, l'ordre de posició se li envia directament. Activa aquesta opció per accionar-la amb obertura/tancament/aturada temporitzats, ignorant-ne la compatibilitat nativa amb l'establiment de posició.",
    "entities.invert": "Inverteix la posició",
    "entities.invert_helper":
      "Inverteix l'eix de posició: informa de 100 − la posició de la persiana embolcallada i intercanvia obertura i tancament. Fes-ho servir per a persianes que funcionen al revés, per exemple un tendal l'entitat subjacent del qual indica obert = desplegat. Només afecta l'eix de posició; la lògica d'inclinació no canvia: està pensat per a cobertes que només tenen posició (tendals/persianes enrotllables), no per a venecianes amb lamel·les orientables.",
    "entities.switch_entities": "Entitats d'interruptor",
    "entities.open_switch": "Interruptor d'obertura",
    "entities.close_switch": "Interruptor de tancament",
    "entities.stop_switch": "Interruptor d'aturada",
    "entities.switch_entities_pulse": "Entitats d'interruptor / script",
    "entities.open_switch_pulse": "Interruptor o script d'obertura",
    "entities.close_switch_pulse": "Interruptor o script de tancament",
    "entities.stop_switch_pulse": "Interruptor o script d'aturada",
    "entities.button": "Botó",
    "tilt.label": "Mode d'inclinació",
    "tilt.none": "No compatible",
    "tilt.sequential_close": "Tanca i després inclina a tancat",
    "tilt.sequential_open": "Tanca i després inclina a obert",
    "tilt.dual_motor": "Motor d'inclinació independent",
    "tilt.inline": "Inclina durant el recorregut",
    "tilt_motor.label": "Motor d'inclinació",
    "tilt_motor.open_switch": "Interruptor d'obertura de la inclinació",
    "tilt_motor.close_switch": "Interruptor de tancament de la inclinació",
    "tilt_motor.stop_switch": "Interruptor d'aturada de la inclinació",
    "tilt_motor.label_pulse": "Motor d'inclinació (interruptor o script)",
    "tilt_motor.open_switch_pulse": "Interruptor o script d'obertura de la inclinació",
    "tilt_motor.close_switch_pulse": "Interruptor o script de tancament de la inclinació",
    "tilt_motor.stop_switch_pulse": "Interruptor o script d'aturada de la inclinació",
    "tilt_motor.safe_position": "Posició d'inclinació segura",
    "tilt_motor.safe_position_helper":
      "La inclinació es mou aquí abans del recorregut (100 = totalment oberta)",
    "tilt_motor.max_allowed_position": "Posició màxima d'inclinació permesa (opcional)",
    "tilt_motor.max_allowed_helper":
      "La inclinació només es permet quan la posició de la persiana és igual o inferior a aquest valor (0 = tancada, 100 = oberta)",
    "tilt.close_includes_tilt": "Tancar la persiana també tanca les lamel·les",
    "tilt.close_includes_tilt_helper":
      "En tancar, les lamel·les s'inclinen a tancat al final del recorregut",
    "assumed_state.label": "Estat suposat",
    "assumed_state.helper":
      "Quan està activat, Home Assistant tracta la posició com a estimada i manté actius els controls d'obertura i tancament. Desactiva-ho si confies en el càlcul per temps i vols que la interfície atenuï les accions no disponibles (per exemple, tancar quan ja està tancada).",
    "relay_reports_off.label": "El relé informa de la seva pròpia desconnexió",
    "relay_reports_off.helper":
      "Deixa-ho activat per als relés de commutació normals, que es desconnecten sols després de l'impuls i ho notifiquen. Desactiva-ho per als mòduls d'impuls gestionats pel maquinari (per exemple, l'Aqara T2), que generen l'impuls internament però no notifiquen mai que s'han desconnectat, i deixen l'entitat d'interruptor encallada en estat activat. Amb l'opció desactivada, la integració només envia una única ordre d'ACTIVACIÓ per pulsació i mai cap de DESACTIVACIÓ, de manera que cada pulsació és exactament una activació neta, sense ordres duplicades.",
    "send_endpoint_stop.label": "Envia un senyal d'aturada als finals de cursa",
    "send_endpoint_stop.helper":
      "Quan la persiana arribi a la posició totalment oberta o tancada, envia l'impuls d'aturada. Mantén aquesta opció activada per als controladors que continuen funcionant fins que reben una aturada (si no, la persiana es queda encallada i els botons físics deixen de respondre). Desactiva-la si el motor s'atura sol als finals de cursa i una aturada addicional el fa anar a una posició predefinida o preferida.",
    "force_endpoint_redrive.label": "Torna a enviar sempre obrir/tancar als finals de cursa",
    "force_endpoint_redrive.helper":
      "Per a persianes sense realimentació de posició que també es poden moure amb un comandament a distància extern, de manera que Home Assistant pot creure erròniament que ja són totalment obertes o tancades. Quan està activat, una ordre d'obrir o tancar s'executa sempre durant tot el temps de recorregut encara que Home Assistant cregui que la persiana ja hi és, cosa que garanteix que l'ordre arriba al motor. Deixa-ho desactivat per a les persianes que informen de la seva pròpia posició.",
    "wait_for_relay_feedback.label": "Espera la confirmació del relé abans de fer el seguiment",
    "wait_for_relay_feedback.helper":
      "Inicia el temporitzador de posició quan el relé informa que s'ha activat, en lloc del moment en què s'envia l'ordre. En una xarxa mallada Zigbee/Z-Wave lenta o freda, l'ordre pot trigar segons a arribar al relé; sense aquesta opció, aquest retard es compta com a recorregut i la posició seguida s'avança a la persiana. Deixa-ho desactivat, tret que la posició es desviï en persianes el relé de les quals respon amb lentitud.",
    "recalibrate_before_position.label": "Obre del tot abans de moure's a una posició (Beta)",
    "recalibrate_before_position.helper":
      "Per a persianes sense realimentació de posició que un comandament a distància també pot moure. Obre la persiana del tot abans de cada ordre de posició, perquè el moviment parteixi d'una posició coneguda en lloc d'una estimació desviada. Duplica aproximadament el recorregut de cada moviment i, amb la inclinació durant el recorregut o la inclinació seqüencial, mou la persiana quan ajustes les lamel·les.",
    "resync.label": "Resincronitza",
    "resync.helper":
      "Indica a la integració la posició real de la persiana després d'haver-la mogut amb el botó físic o un comandament a distància RF. Això reancora el seguiment de la posició i atura el motor si Home Assistant encara l'està accionant; mai no el posa en marxa.",
    more_info: "Més informació",
    "timing.travel_attribute_header": "Atribut de recorregut",
    "timing.tilt_attribute_header": "Atribut d'inclinació",
    "timing.value_header": "Valor",
    "timing.not_set": "Sense definir",
    "timing.travel_time_close": "Temps de recorregut (tancament)",
    "timing.travel_time_open": "Temps de recorregut (obertura)",
    "timing.travel_startup_delay": "Retard d'arrencada del recorregut",
    "timing.tilt_time_close": "Temps d'inclinació (tancament)",
    "timing.tilt_time_open": "Temps d'inclinació (obertura)",
    "timing.tilt_startup_delay": "Retard d'arrencada de la inclinació",
    "timing.min_movement_time": "Temps mínim de moviment",
    "timing.endpoint_runon_time": "Temps de prolongació als finals de cursa",
    "position.label": "Posició actual",
    "position.helper":
      "Mou la persiana a un final de cursa conegut i després estableix la posició.",
    "position.unknown": "Desconeguda",
    "position.open": "Totalment oberta",
    "position.closed": "Totalment tancada",
    "position.closed_tilt_open": "Totalment tancada, inclinació oberta",
    "position.closed_tilt_closed": "Totalment tancada, inclinació tancada",
    "calibration.label": "Calibració de temps",
    "calibration.attribute_label": "Atribut",
    "calibration.start": "Inicia",
    "calibration.active": "Calibració activa",
    "calibration.step": "Pas {step}",
    "calibration.final_step": "Últim pas",
    "calibration.cancel": "Cancel·la",
    "calibration.finish": "Finalitza",
    "calibration.set_position_first": "Estableix la posició per iniciar la calibració.",
    "controls.cover_label": "Persiana",
    "controls.tilt_label": "Inclinació",
    "controls.open": "Obre",
    "controls.stop": "Atura",
    "controls.close": "Tanca",
    "controls.tilt_open": "Obre la inclinació",
    "controls.tilt_stop": "Atura la inclinació",
    "controls.tilt_close": "Tanca la inclinació",
    "hints.sequential_close.travel_time_close":
      "Comença amb la persiana totalment oberta. Fes clic a Finalitza quan la persiana estigui totalment tancada, abans que les lamel·les comencin a inclinar-se.",
    "hints.sequential_close.travel_time_open":
      "Comença amb la persiana tancada i les lamel·les obertes. Fes clic a Finalitza quan la persiana estigui totalment oberta.",
    "hints.sequential_close.tilt_time_close":
      "Comença amb la persiana tancada però les lamel·les obertes. Fes clic a Finalitza quan les lamel·les estiguin totalment tancades.",
    "hints.sequential_close.tilt_time_open":
      "Comença amb la persiana i les lamel·les tancades. Fes clic a Finalitza quan les lamel·les estiguin obertes.",
    "hints.sequential_open.travel_time_close":
      "Comença amb la persiana totalment oberta i les lamel·les tancades. Fes clic a Finalitza quan la persiana estigui totalment tancada, abans que les lamel·les comencin a obrir-se.",
    "hints.sequential_open.travel_time_open":
      "Comença amb la persiana tancada i les lamel·les tancades. Fes clic a Finalitza quan la persiana estigui totalment oberta.",
    "hints.sequential_open.tilt_time_close":
      "Comença amb la persiana tancada però les lamel·les obertes. Fes clic a Finalitza quan les lamel·les estiguin totalment tancades.",
    "hints.sequential_open.tilt_time_open":
      "Comença amb la persiana i les lamel·les tancades. Fes clic a Finalitza quan les lamel·les estiguin totalment obertes.",
    "hints.dual_motor.travel_time_close":
      "Comença amb la persiana oberta i les lamel·les en la posició segura. Fes clic a Finalitza quan la persiana estigui totalment tancada.",
    "hints.dual_motor.travel_time_open":
      "Comença amb la persiana tancada i les lamel·les en la posició segura. Fes clic a Finalitza quan la persiana estigui totalment oberta.",
    "hints.dual_motor.tilt_time_close":
      "Comença amb la persiana tancada i les lamel·les obertes. Fes clic a Finalitza quan les lamel·les estiguin totalment tancades.",
    "hints.dual_motor.tilt_time_open":
      "Comença amb la persiana i les lamel·les tancades. Fes clic a Finalitza quan les lamel·les estiguin totalment obertes.",
    "hints.inline.travel_time_close":
      "Comença amb la persiana i les lamel·les totalment obertes. Fes clic a Finalitza quan totes dues estiguin totalment tancades.",
    "hints.inline.travel_time_open":
      "Comença amb la persiana i les lamel·les totalment tancades. Fes clic a Finalitza quan totes dues estiguin totalment obertes.",
    "hints.inline.tilt_time_close":
      "Comença amb les lamel·les totalment obertes. Fes clic a Finalitza quan les lamel·les estiguin totalment tancades.",
    "hints.inline.tilt_time_open":
      "Comença amb les lamel·les totalment tancades. Fes clic a Finalitza quan les lamel·les estiguin totalment obertes.",
    "hints.none.travel_time_close":
      "Fes clic a Finalitza quan la persiana estigui totalment tancada.",
    "hints.none.travel_time_open":
      "Fes clic a Finalitza quan la persiana estigui totalment oberta.",
    "hints.min_movement_time": "Fes clic a Finalitza tan bon punt notis que la persiana es mou.",
  },
  cs: {
    header: "Konfigurace Cover Time Based",
    loading: "Načítání...",
    saving: "Ukládání...",
    save_failed: "Uložení selhalo — hodnota vrácena",
    confirm_cancel_calibration: "Probíhá kalibrace. Zrušit ji a pokračovat?",
    create_new: "+ Vytvořit novou entitu rolety",
    yaml_warning:
      "Tato entita používá konfiguraci YAML a nelze ji nastavit z této karty. Přejděte prosím na uživatelské rozhraní: Nastavení → Zařízení a služby → Pomocníci → Vytvořit pomocníka → Cover Time Based.",
    load_failed: "Nepodařilo se načíst konfiguraci. Zkuste to prosím znovu.",
    admin_required:
      "Tato karta vyžaduje účet administrátora. Přihlaste se prosím jako administrátor, abyste mohli nastavit rolety.",
    "tabs.device": "Zařízení",
    "tabs.calibration": "Kalibrace",
    "control_mode.label": "Režim ovládání",
    "control_mode.wrapped": "Zabalit existující entitu rolety",
    "control_mode.switch": "Spínač (trvalý)",
    "control_mode.pulse": "Impulz (dočasný)",
    "control_mode.toggle": "Přepínání (stejné tlačítko)",
    "control_mode.toggle_opposite": "Přepínání (opačné tlačítko)",
    "control_mode.single_button": "Jedno tlačítko (cyklické)",
    "control_mode.pulse_time": "Doba impulzu",
    "entities.cover_entity": "Entita rolety",
    "position_reporting.label": "Hlášení pozice",
    "position_reporting.reliable": "Spolehlivá zpětná vazba pozice",
    "position_reporting.reliable_helper":
      "Zabalená roleta hlásí důvěryhodnou pozici a dosahuje svých skutečných koncových poloh otevřeno/zavřeno. Výchozí volba — správná, pokud se sledovaná pozice neodchyluje od toho, kde roleta ve skutečnosti je.",
    "position_reporting.unreliable": "Pozice nespolehlivá — sledovat podle času",
    "position_reporting.unreliable_helper":
      "Sledovat pozici pouze podle času a ignorovat pozici, kterou hlásí zabalená roleta. Zapněte, pokud podkladová roleta hlásí nespolehlivou pozici.",
    "position_reporting.no_endpoints":
      "Žádné skutečné koncové polohy — hlásí otevřeno/zavřeno při zastavení",
    "position_reporting.no_endpoints_helper":
      "Pro rolety bez zpětné vazby pozice, které při zastavení motoru uprostřed pohybu hlásí otevřeno/zavřeno, nikoli pouze ve fyzických koncových polohách. Hlášený stav zavřeno zastaví sledování na vypočtené pozici místo skoku na 0 %.",
    "position_reporting.command_echo": "Stav zrcadlí poslední příkaz",
    "position_reporting.command_echo_helper":
      "Zapněte pro rolety (např. některé rolety Tuya), jejichž stav otevřeno/zavřeno/neznámý je ozvěnou příkazu, nikoli skutečnou koncovou polohou — nehlásí žádný přechod otevírání/zavírání ani pozici. Stav je považován za příkaz otevřít/zavřít/zastavit a pozice se sleduje podle času.",
    "position_reporting.ignore_all": "Ignorovat všechna hlášení zařízení",
    "position_reporting.ignore_all_helper":
      "Stav i poloha zařízení jsou nespolehlivé. Ignorujte vše, co hlásí, a sledujte polohu výhradně podle časů otevírání/zavírání. Home Assistant se stává jediným způsobem, jak roletu ovládat — ovládání nástěnným vypínačem nebo dálkovým ovladačem se nesleduje.",
    "position_reporting.docs_link": "Zjistit více",
    "entities.force_time_based_position": "Vynutit polohování podle času",
    "entities.force_time_based_position_helper":
      "Ve výchozím nastavení, pokud zabalená roleta podporuje nastavení pozice, je příkaz nastavení pozice odeslán přímo jí. Zapnutím ji místo toho budete ovládat časovaným otevřít/zavřít/zastavit a její nativní podpora nastavení pozice se bude ignorovat.",
    "entities.invert": "Invertovat pozici",
    "entities.invert_helper":
      "Převrátí osu pozice: hlásí 100 − pozici zabalené rolety a prohodí otevřít/zavřít. Použijte pro rolety, které jedou obráceně, např. markýzu, kde podkladová entita hlásí otevřeno = vysunuto. Pouze osa pozice; logika náklonu zůstává beze změny — určeno pro rolety pouze s pozicí (markýzy/rolety), nikoli pro naklápěcí žaluzie.",
    "entities.switch_entities": "Entity spínačů",
    "entities.open_switch": "Spínač otevírání",
    "entities.close_switch": "Spínač zavírání",
    "entities.stop_switch": "Spínač zastavení",
    "entities.switch_entities_pulse": "Entity spínačů / skriptů",
    "entities.open_switch_pulse": "Spínač nebo skript otevírání",
    "entities.close_switch_pulse": "Spínač nebo skript zavírání",
    "entities.stop_switch_pulse": "Spínač nebo skript zastavení",
    "entities.button": "Tlačítko",
    "tilt.label": "Režim náklonu",
    "tilt.none": "Nepodporováno",
    "tilt.sequential_close": "Zavře a poté nakloní do zavřeno",
    "tilt.sequential_open": "Zavře a poté nakloní do otevřeno",
    "tilt.dual_motor": "Samostatný motor náklonu",
    "tilt.inline": "Naklání se současně s pohybem",
    "tilt_motor.label": "Motor náklonu",
    "tilt_motor.open_switch": "Spínač otevírání náklonu",
    "tilt_motor.close_switch": "Spínač zavírání náklonu",
    "tilt_motor.stop_switch": "Spínač zastavení náklonu",
    "tilt_motor.label_pulse": "Motor náklonu (spínač nebo skript)",
    "tilt_motor.open_switch_pulse": "Spínač nebo skript otevírání náklonu",
    "tilt_motor.close_switch_pulse": "Spínač nebo skript zavírání náklonu",
    "tilt_motor.stop_switch_pulse": "Spínač nebo skript zastavení náklonu",
    "tilt_motor.safe_position": "Bezpečná pozice náklonu",
    "tilt_motor.safe_position_helper": "Náklon se sem přesune před pohybem (100 = plně otevřeno)",
    "tilt_motor.max_allowed_position": "Maximální povolená pozice náklonu (volitelné)",
    "tilt_motor.max_allowed_helper":
      "Náklon je povolen pouze tehdy, když je pozice rolety na této hodnotě nebo pod ní (0 = zavřeno, 100 = otevřeno)",
    "tilt.close_includes_tilt": "Zavření rolety zavře i lamely",
    "tilt.close_includes_tilt_helper": "Při zavírání se lamely na konci pohybu naklopí do zavřeno",
    "assumed_state.label": "Předpokládaný stav",
    "assumed_state.helper":
      "Když je zapnuto, Home Assistant považuje pozici za odhadovanou a ponechává ovládací prvky otevření i zavření aktivní. Vypněte, pokud důvěřujete výpočtu podle času a chcete, aby rozhraní zešedlo nedostupné akce (např. zavřít, když je již zavřeno).",
    "relay_reports_off.label": "Relé hlásí své vlastní vypnutí (OFF)",
    "relay_reports_off.helper":
      "Ponechte zapnuté pro běžná přepínací relé, která se po impulzu sama vypnou a nahlásí to. Vypněte pro pulzní moduly řízené hardwarem (např. Aqara T2), které pulzují interně, ale nikdy nenahlásí, když se vypnou, takže entita spínače zůstane zaseknutá v zapnutém stavu. Když je vypnuto, integrace odešle na jeden stisk vždy pouze jeden příkaz ZAPNOUT (ON) a nikdy VYPNOUT (OFF) — takže každý stisk je přesně jedna čistá aktivace bez zdvojených příkazů.",
    "send_endpoint_stop.label": "Odeslat signál zastavení v koncových polohách",
    "send_endpoint_stop.helper":
      "Když vaše roleta dosáhne plně otevřeno nebo zavřeno, odešle se impulz zastavení. Ponechte zapnuté pro ovladače, které běží dál, dokud neobdrží zastavení (jinak se roleta zasekne a fyzická tlačítka přestanou reagovat). Vypněte, pokud se váš motor v koncových polohách zastaví sám a další zastavení jej přesune do přednastavené/oblíbené pozice.",
    "force_endpoint_redrive.label": "V koncových polohách vždy znovu odeslat otevřít/zavřít",
    "force_endpoint_redrive.helper":
      "Pro rolety bez zpětné vazby pozice, které lze ovládat i externím dálkovým ovladačem, takže se Home Assistant může mylně domnívat, že jsou již plně otevřené nebo zavřené. Když je zapnuto, příkaz otevřít nebo zavřít je vždy vykonán po celou dobu pohybu, i když si Home Assistant myslí, že tam roleta již je — čímž se zaručí, že příkaz dorazí k motoru. Ponechte vypnuté pro rolety, které hlásí svou vlastní pozici.",
    "wait_for_relay_feedback.label": "Před sledováním počkat na potvrzení relé",
    "wait_for_relay_feedback.helper":
      "Spustí časovač pozice ve chvíli, kdy relé nahlásí, že se zaplo, místo v okamžiku odeslání příkazu. V pomalé nebo studené síti Zigbee/Z-Wave může příkazu trvat několik sekund, než dorazí k relé; bez této volby se toto zpoždění počítá jako pohyb a sledovaná pozice předbíhá roletu. Ponechte vypnuté, pokud se pozice neodchyluje u rolet, jejichž relé reaguje pomalu.",
    "recalibrate_before_position.label": "Před přesunem na pozici plně otevřít (Beta)",
    "recalibrate_before_position.helper":
      "Pro rolety bez zpětné vazby pozice, kterými může pohybovat i dálkový ovladač. Před každým příkazem na pozici roletu plně otevře, takže pohyb začíná ze známé pozice místo z odchýleného odhadu. Zhruba zdvojnásobí dráhu každého pohybu a u současného nebo sekvenčního náklonu pohne roletou, když upravujete lamely.",
    "resync.label": "Resynchronizace",
    "resync.helper":
      "Sdělte integraci skutečnou polohu rolety poté, co byla pohnuta fyzickým tlačítkem nebo RF dálkovým ovladačem. Tím se znovu ukotví sledování polohy a zastaví se motor, pokud jej Home Assistant stále ovládá; nikdy jej tím nespustí.",
    more_info: "Více informací",
    "timing.travel_attribute_header": "Atribut pohybu",
    "timing.tilt_attribute_header": "Atribut náklonu",
    "timing.value_header": "Hodnota",
    "timing.not_set": "Nenastaveno",
    "timing.travel_time_close": "Doba pohybu (zavírání)",
    "timing.travel_time_open": "Doba pohybu (otevírání)",
    "timing.travel_startup_delay": "Prodleva rozjezdu pohybu",
    "timing.tilt_time_close": "Doba náklonu (zavírání)",
    "timing.tilt_time_open": "Doba náklonu (otevírání)",
    "timing.tilt_startup_delay": "Prodleva rozjezdu náklonu",
    "timing.min_movement_time": "Minimální doba pohybu",
    "timing.endpoint_runon_time": "Doba doběhu v koncové poloze",
    "position.label": "Aktuální pozice",
    "position.helper": "Přesuňte roletu do známé koncové polohy a poté nastavte pozici.",
    "position.unknown": "Neznámá",
    "position.open": "Plně otevřeno",
    "position.closed": "Plně zavřeno",
    "position.closed_tilt_open": "Plně zavřeno, náklon otevřen",
    "position.closed_tilt_closed": "Plně zavřeno, náklon zavřen",
    "calibration.label": "Kalibrace časování",
    "calibration.attribute_label": "Atribut",
    "calibration.start": "Spustit",
    "calibration.active": "Kalibrace probíhá",
    "calibration.step": "Krok {step}",
    "calibration.final_step": "Poslední krok",
    "calibration.cancel": "Zrušit",
    "calibration.finish": "Dokončit",
    "calibration.set_position_first": "Nastavte pozici pro spuštění kalibrace.",
    "controls.cover_label": "Roleta",
    "controls.tilt_label": "Náklon",
    "controls.open": "Otevřít",
    "controls.stop": "Zastavit",
    "controls.close": "Zavřít",
    "controls.tilt_open": "Otevřít náklon",
    "controls.tilt_stop": "Zastavit náklon",
    "controls.tilt_close": "Zavřít náklon",
    "hints.sequential_close.travel_time_close":
      "Začněte s plně otevřenou roletou. Klikněte na Dokončit, když je roleta plně zavřená, dříve než se lamely začnou naklánět.",
    "hints.sequential_close.travel_time_open":
      "Začněte se zavřenou roletou a otevřenými lamelami. Klikněte na Dokončit, když je roleta plně otevřená.",
    "hints.sequential_close.tilt_time_close":
      "Začněte se zavřenou roletou, ale otevřenými lamelami. Klikněte na Dokončit, když jsou lamely plně zavřené.",
    "hints.sequential_close.tilt_time_open":
      "Začněte se zavřenou roletou i lamelami. Klikněte na Dokončit, když jsou lamely otevřené.",
    "hints.sequential_open.travel_time_close":
      "Začněte s plně otevřenou roletou a zavřenými lamelami. Klikněte na Dokončit, když je roleta plně zavřená, dříve než se lamely začnou naklánět do otevřeno.",
    "hints.sequential_open.travel_time_open":
      "Začněte se zavřenou roletou i zavřenými lamelami. Klikněte na Dokončit, když je roleta plně otevřená.",
    "hints.sequential_open.tilt_time_close":
      "Začněte se zavřenou roletou, ale otevřenými lamelami. Klikněte na Dokončit, když jsou lamely plně zavřené.",
    "hints.sequential_open.tilt_time_open":
      "Začněte se zavřenou roletou i lamelami. Klikněte na Dokončit, když jsou lamely plně otevřené.",
    "hints.dual_motor.travel_time_close":
      "Začněte s otevřenou roletou a lamelami v bezpečné pozici. Klikněte na Dokončit, když je roleta plně zavřená.",
    "hints.dual_motor.travel_time_open":
      "Začněte se zavřenou roletou a lamelami v bezpečné pozici. Klikněte na Dokončit, když je roleta plně otevřená.",
    "hints.dual_motor.tilt_time_close":
      "Začněte se zavřenou roletou a otevřenými lamelami. Klikněte na Dokončit, když jsou lamely plně zavřené.",
    "hints.dual_motor.tilt_time_open":
      "Začněte se zavřenou roletou i lamelami. Klikněte na Dokončit, když jsou lamely plně otevřené.",
    "hints.inline.travel_time_close":
      "Začněte s plně otevřenou roletou i lamelami. Klikněte na Dokončit, když jsou obě plně zavřené.",
    "hints.inline.travel_time_open":
      "Začněte s plně zavřenou roletou i lamelami. Klikněte na Dokončit, když jsou obě plně otevřené.",
    "hints.inline.tilt_time_close":
      "Začněte s plně otevřenými lamelami. Klikněte na Dokončit, když jsou lamely plně zavřené.",
    "hints.inline.tilt_time_open":
      "Začněte s plně zavřenými lamelami. Klikněte na Dokončit, když jsou lamely plně otevřené.",
    "hints.none.travel_time_close": "Klikněte na Dokončit, když je roleta plně zavřená.",
    "hints.none.travel_time_open": "Klikněte na Dokončit, když je roleta plně otevřená.",
    "hints.min_movement_time": "Klikněte na Dokončit, jakmile zaznamenáte, že se roleta pohybuje.",
  },
  "sr-Latn": {
    header: "Konfiguracija Cover Time Based",
    loading: "Učitavanje...",
    saving: "Čuvanje...",
    save_failed: "Čuvanje nije uspelo — vrednost je vraćena",
    confirm_cancel_calibration: "Kalibracija je u toku. Otkazati je i nastaviti?",
    create_new: "+ Kreiraj novi entitet roletne",
    yaml_warning:
      "Ovaj entitet koristi YAML konfiguraciju i ne može se podesiti sa ove kartice. Pređite na korisnički interfejs: Podešavanja → Uređaji i usluge → Pomoćnici → Kreirajte pomoćnika → Cover Time Based.",
    load_failed: "Učitavanje konfiguracije nije uspelo. Pokušajte ponovo.",
    admin_required:
      "Ova kartica zahteva administratorski nalog. Prijavite se kao administrator da biste podesili roletne.",
    "tabs.device": "Uređaj",
    "tabs.calibration": "Kalibracija",
    "control_mode.label": "Režim upravljanja",
    "control_mode.wrapped": "Omotaj postojeći entitet roletne",
    "control_mode.switch": "Prekidač (zadržava stanje)",
    "control_mode.pulse": "Impuls (trenutni)",
    "control_mode.toggle": "Naizmenično (isto dugme)",
    "control_mode.toggle_opposite": "Naizmenično (suprotno dugme)",
    "control_mode.single_button": "Jedno dugme (ciklično)",
    "control_mode.pulse_time": "Trajanje impulsa",
    "entities.cover_entity": "Entitet roletne",
    "position_reporting.label": "Prijavljivanje pozicije",
    "position_reporting.reliable": "Pouzdana povratna informacija o poziciji",
    "position_reporting.reliable_helper":
      "Omotana roletna prijavljuje pouzdanu poziciju i dostiže svoje stvarne krajnje položaje otvoreno/zatvoreno. Podrazumevana opcija — pravi izbor osim ako praćena pozicija ne odstupa od stvarnog položaja roletne.",
    "position_reporting.unreliable": "Pozicija nepouzdana — prati po vremenu",
    "position_reporting.unreliable_helper":
      "Prati poziciju samo po vremenu i zanemari poziciju koju prijavljuje omotana roletna. Omogućite ovo ako osnovna roletna prijavljuje nepouzdanu poziciju.",
    "position_reporting.no_endpoints":
      "Bez stvarnih krajnjih položaja — prijavljuje otvoreno/zatvoreno pri zaustavljanju",
    "position_reporting.no_endpoints_helper":
      "Za roletne bez povratne informacije o poziciji koje prijavljuju otvoreno/zatvoreno kada se motor zaustavi usred kretanja, a ne samo na fizičkim krajnjim položajima. Prijavljeno stanje „zatvoreno“ zaustavlja praćenje na izračunatoj poziciji umesto da skoči na 0%.",
    "position_reporting.command_echo": "Stanje odražava poslednju komandu",
    "position_reporting.command_echo_helper":
      "Omogućite za roletne (npr. neke Tuya roletne) čije stanje otvoreno/zatvoreno/nepoznato predstavlja odjek komande, a ne stvaran krajnji položaj — ne prijavljuju prelaz otvaranja/zatvaranja niti poziciju. Stanje se tretira kao komanda otvori/zatvori/zaustavi, a pozicija se prati po vremenu.",
    "position_reporting.ignore_all": "Zanemari sve izveštaje uređaja",
    "position_reporting.ignore_all_helper":
      "Stanje i pozicija uređaja su nepouzdani. Zanemarite sve što uređaj prijavljuje i pratite poziciju isključivo po tajmerima otvaranja/zatvaranja. Home Assistant postaje jedini način da se roletna pomeri — rukovanje zidnim prekidačem ili daljinskim upravljačem se ne prati.",
    "position_reporting.docs_link": "Saznajte više",
    "entities.force_time_based_position": "Prinudno pozicioniranje po vremenu",
    "entities.force_time_based_position_helper":
      "Podrazumevano, ako omotana roletna podržava postavljanje pozicije, komanda za postavljanje pozicije joj se šalje direktno. Omogućite ovo da biste je umesto toga pokretali vremenski određenim komandama otvori/zatvori/zaustavi, zanemarujući njenu ugrađenu podršku za postavljanje pozicije.",
    "entities.invert": "Obrni poziciju",
    "entities.invert_helper":
      "Obrće osu pozicije: prijavljuje 100 − poziciju omotane roletne i zamenjuje otvori/zatvori. Koristite za roletne koje rade obrnuto, npr. tendu kod koje osnovni entitet prijavljuje otvoreno = razvučeno. Samo osa pozicije; logika nagiba je nepromenjena — namenjeno roletnama samo sa pozicijom (tende/roletne), ne venecijanerima koji se naginju.",
    "entities.switch_entities": "Entiteti prekidača",
    "entities.open_switch": "Prekidač za otvaranje",
    "entities.close_switch": "Prekidač za zatvaranje",
    "entities.stop_switch": "Prekidač za zaustavljanje",
    "entities.switch_entities_pulse": "Entiteti prekidača / skripti",
    "entities.open_switch_pulse": "Prekidač ili skripta za otvaranje",
    "entities.close_switch_pulse": "Prekidač ili skripta za zatvaranje",
    "entities.stop_switch_pulse": "Prekidač ili skripta za zaustavljanje",
    "entities.button": "Dugme",
    "tilt.label": "Režim nagiba",
    "tilt.none": "Nije podržano",
    "tilt.sequential_close": "Zatvara pa naginje u zatvoreno",
    "tilt.sequential_open": "Zatvara pa naginje u otvoreno",
    "tilt.dual_motor": "Zaseban motor za nagib",
    "tilt.inline": "Naginje istovremeno sa kretanjem",
    "tilt_motor.label": "Motor za nagib",
    "tilt_motor.open_switch": "Prekidač za otvaranje nagiba",
    "tilt_motor.close_switch": "Prekidač za zatvaranje nagiba",
    "tilt_motor.stop_switch": "Prekidač za zaustavljanje nagiba",
    "tilt_motor.label_pulse": "Motor za nagib (prekidač ili skripta)",
    "tilt_motor.open_switch_pulse": "Prekidač ili skripta za otvaranje nagiba",
    "tilt_motor.close_switch_pulse": "Prekidač ili skripta za zatvaranje nagiba",
    "tilt_motor.stop_switch_pulse": "Prekidač ili skripta za zaustavljanje nagiba",
    "tilt_motor.safe_position": "Bezbedna pozicija nagiba",
    "tilt_motor.safe_position_helper": "Nagib se pomera ovde pre kretanja (100 = potpuno otvoreno)",
    "tilt_motor.max_allowed_position": "Najveća dozvoljena pozicija nagiba (opciono)",
    "tilt_motor.max_allowed_helper":
      "Nagib je dozvoljen samo kada je pozicija roletne na ovoj vrednosti ili ispod nje (0 = zatvoreno, 100 = otvoreno)",
    "tilt.close_includes_tilt": "Zatvaranje roletne zatvara i lamele",
    "tilt.close_includes_tilt_helper":
      "Pri zatvaranju, lamele se naginju u zatvoreno na kraju kretanja",
    "assumed_state.label": "Pretpostavljeno stanje",
    "assumed_state.helper":
      "Kada je uključeno, Home Assistant tretira poziciju kao procenjenu i drži i kontrolu za otvaranje i za zatvaranje aktivnima. Isključite ako verujete proračunu na osnovu vremena i želite da interfejs zasivi nedostupne radnje (npr. zatvaranje kada je već zatvoreno).",
    "relay_reports_off.label": "Relej prijavljuje sopstveno isključenje",
    "relay_reports_off.helper":
      "Ostavite uključeno za uobičajene naizmenične releje, koji se sami isključe nakon impulsa i to prijave. Isključite za hardverski upravljane impulsne module (npr. Aqara T2) koji impuls generišu interno, ali nikada ne prijave kada se isključe, ostavljajući entitet prekidača zaglavljen u uključenom stanju. Kada je isključeno, integracija po svakom pritisku šalje samo jednu komandu UKLJUČI i nikada ISKLJUČI — pa je svaki pritisak tačno jedna čista aktivacija, bez udvostručenih komandi.",
    "send_endpoint_stop.label": "Pošalji signal zaustavljanja na krajnjim položajima",
    "send_endpoint_stop.helper":
      "Kada vaša roletna dostigne potpuno otvoreno ili zatvoreno, pošaljite impuls zaustavljanja. Ostavite uključeno za kontrolere koji nastavljaju da rade dok ne prime zaustavljanje (roletna se u suprotnom zaglavi i fizička dugmad prestanu da reaguju). Isključite ako se vaš motor sam zaustavlja na svojim granicama i dodatno zaustavljanje ga pomera na unapred podešenu/omiljenu poziciju.",
    "force_endpoint_redrive.label": "Uvek ponovo pošalji otvori/zatvori na krajnjim položajima",
    "force_endpoint_redrive.helper":
      "Za roletne bez povratne informacije o poziciji koje se mogu pomerati i spoljnim daljinskim upravljačem, pa Home Assistant može pogrešno smatrati da su već potpuno otvorene ili zatvorene. Kada je uključeno, komanda otvaranja ili zatvaranja se uvek izvršava tokom celog vremena kretanja, čak i ako Home Assistant misli da je roletna već tamo — čime se garantuje da komanda stigne do motora. Ostavite isključeno za roletne koje prijavljuju sopstvenu poziciju.",
    "wait_for_relay_feedback.label": "Sačekaj potvrdu releja pre praćenja",
    "wait_for_relay_feedback.helper":
      "Pokreće tajmer pozicije kada relej prijavi da se uključio, umesto u trenutku slanja komande. Na sporoj ili hladnoj Zigbee/Z-Wave mreži komandi može trebati nekoliko sekundi da stigne do releja; bez ovoga se to kašnjenje računa kao kretanje i praćena pozicija izmiče ispred roletne. Ostavite isključeno osim ako pozicija ne odstupa kod roletni čiji relej sporo reaguje.",
    "recalibrate_before_position.label": "Potpuno otvori pre pomeranja na poziciju (Beta)",
    "recalibrate_before_position.helper":
      "Za roletne bez povratne informacije o poziciji koje daljinski upravljač takođe može da pomera. Pre svake komande za poziciju roletnu potpuno otvara, pa kretanje počinje od poznate pozicije umesto od izmaknute procene. Otprilike udvostručuje kretanje pri svakom pomeranju, a kod istovremenog ili sekvencijalnog nagiba pomera roletnu kada podešavate lamele.",
    "resync.label": "Ponovna sinhronizacija",
    "resync.helper":
      "Recite integraciji stvarnu poziciju roletne nakon što je pomerena fizičkim dugmetom ili RF daljinskim upravljačem. Ovo ponovo usidrava praćenje pozicije i zaustavlja motor ako njime Home Assistant i dalje upravlja; nikada ga ne pokreće.",
    more_info: "Više informacija",
    "timing.travel_attribute_header": "Atribut kretanja",
    "timing.tilt_attribute_header": "Atribut nagiba",
    "timing.value_header": "Vrednost",
    "timing.not_set": "Nije postavljeno",
    "timing.travel_time_close": "Vreme kretanja (zatvaranje)",
    "timing.travel_time_open": "Vreme kretanja (otvaranje)",
    "timing.travel_startup_delay": "Kašnjenje pokretanja kretanja",
    "timing.tilt_time_close": "Vreme nagiba (zatvaranje)",
    "timing.tilt_time_open": "Vreme nagiba (otvaranje)",
    "timing.tilt_startup_delay": "Kašnjenje pokretanja nagiba",
    "timing.min_movement_time": "Minimalno vreme kretanja",
    "timing.endpoint_runon_time": "Vreme prekoračenja na krajnjem položaju",
    "position.label": "Trenutna pozicija",
    "position.helper": "Pomerite roletnu na poznati krajnji položaj, pa postavite poziciju.",
    "position.unknown": "Nepoznato",
    "position.open": "Potpuno otvoreno",
    "position.closed": "Potpuno zatvoreno",
    "position.closed_tilt_open": "Potpuno zatvoreno, nagib otvoren",
    "position.closed_tilt_closed": "Potpuno zatvoreno, nagib zatvoren",
    "calibration.label": "Kalibracija vremena",
    "calibration.attribute_label": "Atribut",
    "calibration.start": "Pokreni",
    "calibration.active": "Kalibracija je aktivna",
    "calibration.step": "Korak {step}",
    "calibration.final_step": "Poslednji korak",
    "calibration.cancel": "Otkaži",
    "calibration.finish": "Završi",
    "calibration.set_position_first": "Postavite poziciju da biste pokrenuli kalibraciju.",
    "controls.cover_label": "Roletna",
    "controls.tilt_label": "Nagib",
    "controls.open": "Otvori",
    "controls.stop": "Zaustavi",
    "controls.close": "Zatvori",
    "controls.tilt_open": "Otvori nagib",
    "controls.tilt_stop": "Zaustavi nagib",
    "controls.tilt_close": "Zatvori nagib",
    "hints.sequential_close.travel_time_close":
      "Počnite sa potpuno otvorenom roletnom. Kliknite na Završi kada je roletna potpuno zatvorena, pre nego što lamele počnu da se naginju.",
    "hints.sequential_close.travel_time_open":
      "Počnite sa zatvorenom roletnom i otvorenim lamelama. Kliknite na Završi kada je roletna potpuno otvorena.",
    "hints.sequential_close.tilt_time_close":
      "Počnite sa zatvorenom roletnom ali otvorenim lamelama. Kliknite na Završi kada su lamele potpuno zatvorene.",
    "hints.sequential_close.tilt_time_open":
      "Počnite sa zatvorenom roletnom i lamelama. Kliknite na Završi kada su lamele otvorene.",
    "hints.sequential_open.travel_time_close":
      "Počnite sa potpuno otvorenom roletnom i zatvorenim lamelama. Kliknite na Završi kada je roletna potpuno zatvorena, pre nego što lamele počnu da se naginju u otvoreno.",
    "hints.sequential_open.travel_time_open":
      "Počnite sa zatvorenom roletnom i zatvorenim lamelama. Kliknite na Završi kada je roletna potpuno otvorena.",
    "hints.sequential_open.tilt_time_close":
      "Počnite sa zatvorenom roletnom ali otvorenim lamelama. Kliknite na Završi kada su lamele potpuno zatvorene.",
    "hints.sequential_open.tilt_time_open":
      "Počnite sa zatvorenom roletnom i lamelama. Kliknite na Završi kada su lamele potpuno otvorene.",
    "hints.dual_motor.travel_time_close":
      "Počnite sa otvorenom roletnom i lamelama u bezbednom položaju. Kliknite na Završi kada je roletna potpuno zatvorena.",
    "hints.dual_motor.travel_time_open":
      "Počnite sa zatvorenom roletnom i lamelama u bezbednom položaju. Kliknite na Završi kada je roletna potpuno otvorena.",
    "hints.dual_motor.tilt_time_close":
      "Počnite sa zatvorenom roletnom i otvorenim lamelama. Kliknite na Završi kada su lamele potpuno zatvorene.",
    "hints.dual_motor.tilt_time_open":
      "Počnite sa zatvorenom roletnom i lamelama. Kliknite na Završi kada su lamele potpuno otvorene.",
    "hints.inline.travel_time_close":
      "Počnite sa potpuno otvorenom roletnom i lamelama. Kliknite na Završi kada su i roletna i lamele potpuno zatvorene.",
    "hints.inline.travel_time_open":
      "Počnite sa potpuno zatvorenom roletnom i lamelama. Kliknite na Završi kada su i roletna i lamele potpuno otvorene.",
    "hints.inline.tilt_time_close":
      "Počnite sa potpuno otvorenim lamelama. Kliknite na Završi kada su lamele potpuno zatvorene.",
    "hints.inline.tilt_time_open":
      "Počnite sa potpuno zatvorenim lamelama. Kliknite na Završi kada su lamele potpuno otvorene.",
    "hints.none.travel_time_close": "Kliknite na Završi kada je roletna potpuno zatvorena.",
    "hints.none.travel_time_open": "Kliknite na Završi kada je roletna potpuno otvorena.",
    "hints.min_movement_time": "Kliknite na Završi čim primetite da se roletna kreće.",
  },
};

/**
 * The TRANSLATIONS key covering `raw`, or "" when nothing does.
 *
 * Tries the exact (region-specific) code first, then its base language, so a
 * pt-BR user reads European Portuguese rather than falling through to English,
 * while a dedicated pt-BR catalogue would still win if one were ever added.
 *
 * Separators are normalised (pt_BR -> pt-BR) but case is not: hass.language is
 * always one of HA's canonical codes with the region already correctly cased,
 * so exact lookups line up. Only the base is lowercased.
 *
 * The separator rule lives in {@link normaliseLocale} so callers that need the
 * canonical code for their own purposes — the banner keys dismissals, display
 * names and issue URLs off it — cannot drift from what resolution uses.
 */
export function normaliseLocale(raw) {
  return (raw || "").replace(/_/g, "-");
}

export function resolveLocale(raw) {
  const code = normaliseLocale(raw);
  if (!code) return "";
  // hasOwn, not `in`: `in` walks the prototype chain, so "constructor" and
  // friends would read as shipped catalogues.
  if (Object.hasOwn(TRANSLATIONS, code)) return code;
  const base = code.split("-")[0].toLowerCase();
  return Object.hasOwn(TRANSLATIONS, base) ? base : "";
}

/**
 * Whether a shipped catalogue covers `raw` — i.e. whether to suppress the
 * "request a translation" banner. A missing or undeterminable language counts
 * as supported: it renders in English anyway, and nagging on it would be noise.
 */
export function isLanguageSupported(raw) {
  if (!raw) return true;
  return resolveLocale(raw) !== "";
}

export function translate(lang, key, replacements) {
  const strings = TRANSLATIONS[resolveLocale(lang)] || EN;
  let str = strings[key] || EN[key] || key;
  if (replacements) {
    for (const [k, v] of Object.entries(replacements)) {
      // split/join, not replace(): replace() substitutes only the first
      // occurrence and interprets $&, $` and $' in the replacement value.
      str = str.split(`{${k}}`).join(v);
    }
  }
  return str;
}
