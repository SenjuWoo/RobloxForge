"""Structured error contract.

Every failure an agent can hit is a ForgeError with {code, message, hint}.
Codes are stable strings; agents may branch on them.

    RBF-STUDIO-*   Roblox Studio installation / process / settings
    RBF-MCP-*      official Studio MCP launcher / handshake
    RBF-DOCS-*     creator-docs cache
    RBF-PROJECT-*  project detection / analysis
    RBF-TOOLS-*    optional Luau toolchain
    RBF-TYPES-*    Roblox type definitions for luau-lsp (download / digest)
    RBF-VERIFY-*   verification contract / receipts
    RBF-AGENT-*    agent config + skill installation
    RBF-ARG-*      caller supplied bad input
"""


class ExitCode:
    OK = 0
    GENERIC = 1
    VALIDATION = 2
    NOT_FOUND = 3
    DEPENDENCY = 4
    REFUSED = 5


# code prefix -> exit code
_EXIT_BY_PREFIX = {
    "RBF-ARG": ExitCode.VALIDATION,
    "RBF-STUDIO": ExitCode.NOT_FOUND,
    "RBF-MCP": ExitCode.DEPENDENCY,
    "RBF-DOCS": ExitCode.DEPENDENCY,
    "RBF-PROJECT": ExitCode.NOT_FOUND,
    "RBF-TOOLS": ExitCode.DEPENDENCY,
    "RBF-TYPES": ExitCode.DEPENDENCY,
    "RBF-VERIFY": ExitCode.VALIDATION,
    "RBF-AGENT": ExitCode.GENERIC,
}


class ForgeError(Exception):
    """Machine-readable failure. Never raise a bare Exception at a boundary."""

    def __init__(self, code, message, hint=None, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}

    @property
    def exit_code(self):
        prefix = "-".join(self.code.split("-")[:2])
        return _EXIT_BY_PREFIX.get(prefix, ExitCode.GENERIC)

    def to_dict(self):
        out = {"ok": False, "error": {"code": self.code, "message": self.message}}
        if self.hint:
            out["error"]["hint"] = self.hint
        if self.details:
            out["error"]["details"] = self.details
        return out

    def __str__(self):
        s = "%s: %s" % (self.code, self.message)
        if self.hint:
            s += "\n  hint: %s" % self.hint
        return s
