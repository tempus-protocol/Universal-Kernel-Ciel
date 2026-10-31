Local policy firewall for coding agents. Client component of [Tempus Guard for GitHub](https://github.com/Julio-Patron/tempus-ddb).

# Ciel Gate

**Categoría:** Agent Change Control / Policy Firewall for Coding Agents.

> **Un firewall local de cambios para agentes de programación:** recibe un diff o comando propuesto por un agente, aplica políticas deterministas, exige aprobación cuando corresponde, ejecuta validaciones bajo allowlist y registra la decisión en un ledger resistente a manipulación.

## Lo único que hace

> **Decide si un cambio propuesto por un agente puede entrar al repositorio.**

Entrada:
* diff unificado;
* identidad del agente;
* commit base;
* rutas modificadas;
* política YAML;
* checks permitidos.

Salida:
* `allow`;
* `deny`;
* `require_approval`;
* explicación estructurada;
* evidencia de validación;
* entrada criptográfica en el ledger.

## CLI 1.0

Solo cuatro comandos:

```bash
ciel-gate init
ciel-gate check
ciel-gate ledger verify
ciel-gate policy validate
```

Exit codes:
* 0  allow
* 2  require_approval
* 3  deny
* 4  input_or_policy_error
* 5  required_check_failed

Esto permite integrarlo directamente en agentes, Git hooks y CI.

## Variables de entorno opcionales

Ciel Gate debe funcionar offline inmediatamente.

```bash
CIEL_GATE_ENABLE_EXEC=0
CIEL_GATE_ALLOWED_COMMANDS=pytest,python,git
CIEL_GATE_EXEC_TIMEOUT=30
CIEL_GATE_LEDGER_PATH=.ciel/decisions.log
CIEL_GATE_REQUIRE_APPROVAL_TTY=1
```

## Valor diferencial

* **Modelo agnóstico**: No importa si el cambio proviene de Codex, Claude Code, Cursor, Copilot, un MCP o un script interno.
* **Local-first y determinista**: La decisión crítica no depende de enviar el repositorio a un proveedor ni de confiar en que un LLM interprete correctamente el riesgo.
* **Trazabilidad resistente a alteraciones**: El ledger demuestra qué diff se evaluó, contra qué política y commit.
* **Fricción B2A casi cero**: Un agente ejecuta un comando, consume JSON y respeta el exit code.
