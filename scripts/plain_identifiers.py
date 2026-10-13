#!/usr/bin/env python3
"""Rewrite Verilog escaped identifiers as plain identifiers.

Spade emits escaped names such as `\\std::cdc::sync2[1546] ` and `\\clk `.
GowinSynthesis accepts them, but Gowin's place and route rejects the netlist
some of them turn into (notably Spade's `\\_ ` for anonymous registers), so the
Gowin flow runs the Spade output through this first. Names are mapped deterministically (non-identifier characters become
`_`), with a numeric suffix whenever that would collide with another name.
String literals and comments are left untouched.

It also replaces constant bit-select indices with literals: Spade writes
`x.as_bits()[1]` as `v[_e_N]` with `localparam[0:0] _e_N = 1;`, and Gowin EDA
(V1.9.12.04) selects bit 0 there instead of bit 1. That flipped the sign of
the sine lookups on hardware (camera upside down, spheres misplaced), so every
`v[param]` becomes `v[<value>]`.

usage: plain_identifiers.py IN.sv OUT.v
"""
import re
import sys

PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")

# IEEE 1800-2017 reserved words: an escaped `\\input ` must not become `input`.
KEYWORDS = set("""
accept_on alias always always_comb always_ff always_latch and assert assign assume automatic
before begin bind bins binsof bit break buf bufif0 bufif1 byte case casex casez cell chandle
checker class clocking cmos config const constraint context continue cover covergroup coverpoint
cross deassign default defparam design disable dist do edge else end endcase endchecker endclass
endclocking endconfig endfunction endgenerate endgroup endinterface endmodule endpackage
endprimitive endprogram endproperty endspecify endsequence endtable endtask enum event eventually
expect export extends extern final first_match for force foreach forever fork forkjoin function
generate genvar global highz0 highz1 if iff ifnone ignore_bins illegal_bins implements implies
import incdir include initial inout input inside instance int integer interconnect interface
intersect join join_any join_none large let liblist library local localparam logic longint
macromodule matches medium modport module nand negedge nettype new nexttime nmos nor
noshowcancelled not notif0 notif1 null or output package packed parameter pmos posedge primitive
priority program property protected pull0 pull1 pulldown pullup pulsestyle_ondetect
pulsestyle_onevent pure rand randc randcase randsequence rcmos real realtime ref reg reject_on
release repeat restrict return rnmos rpmos rtran rtranif0 rtranif1 s_always s_eventually
s_nexttime s_until s_until_with scalared sequence shortint shortreal showcancelled signed small
soft solve specify specparam static string strong strong0 strong1 struct super supply0 supply1
sync_accept_on sync_reject_on table tagged task this throughout time timeprecision timeunit tran
tranif0 tranif1 tri tri0 tri1 triand trior trireg type typedef union unique unique0 unsigned
until until_with untyped use uwire var vectored virtual void wait wait_order wand weak weak0
weak1 while wildcard wire with within wor xnor xor
""".split())


def tokens(src):
    """Yield (kind, text): 'esc' for escaped identifiers, 'other' for the rest."""
    i, n = 0, len(src)
    start = 0
    while i < n:
        c = src[i]
        if c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "\\":
            if i > start:
                yield "other", src[start:i]
            j = i + 1
            while j < n and not src[j].isspace():
                j += 1
            yield "esc", src[i + 1:j]
            i = start = j
            continue
        else:
            i += 1
            continue
    if start < n:
        yield "other", src[start:]


def main():
    src = open(sys.argv[1]).read()
    parts = list(tokens(src))
    used = set()
    for kind, text in parts:
        if kind == "other":
            used.update(PLAIN.findall(text))
    mapping = {}
    # `\clk ` is the same identifier as `clk`: keep those first so no
    # generated name can take them.
    for kind, text in parts:
        if kind == "esc" and PLAIN.fullmatch(text) and text not in KEYWORDS and text.strip("_"):
            mapping[text] = text
            used.add(text)
    for kind, text in parts:
        if kind != "esc" or text in mapping:
            continue
        # Gowin's place and route also rejects names made only of underscores
        # (Spade uses `_` for anonymous registers), so those become `anon`.
        base = re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_") or "anon"
        if base[0].isdigit() or base in KEYWORDS:
            base = "_" + base
        name, k = base, 1
        while name in used:
            name = f"{base}_{k}"
            k += 1
        mapping[text] = name
        used.add(name)
    out = "".join(mapping[t] + " " if kind == "esc" else t for kind, t in parts)
    open(sys.argv[2], "w").write(literal_indices(out))


LOCALPARAM = re.compile(r"localparam\s*\[\s*(\d+)\s*:\s*0\s*\]\s*([A-Za-z_]\w*)\s*=\s*(-?)(?:\d+'d)?(\d+)\s*;")


def literal_indices(src):
    """Within each module, rewrite `name[param]` bit-selects to `name[value]`."""
    out = []
    pos = 0
    for m in re.finditer(r"\bmodule\b.*?\bendmodule\b", src, re.S):
        out.append(src[pos:m.start()])
        body = m.group(0)
        consts = {}
        for d in LOCALPARAM.finditer(body):
            width, name, neg, value = int(d.group(1)) + 1, d.group(2), d.group(3), int(d.group(4))
            consts[name] = (-value if neg else value) % (1 << width)
        if consts:
            body = re.sub(r"(\b[A-Za-z_]\w*\s*)\[\s*([A-Za-z_]\w*)\s*\]",
                          lambda b: f"{b.group(1)}[{consts[b.group(2)]}]" if b.group(2) in consts else b.group(0),
                          body)
        out.append(body)
        pos = m.end()
    out.append(src[pos:])
    return "".join(out)


if __name__ == "__main__":
    main()
