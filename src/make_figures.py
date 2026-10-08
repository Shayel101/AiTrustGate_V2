"""Generate the A2 figures into figures/ (PNG). Diagrams mirror the code; metric figures use real model scores.

Usage:  python src/make_figures.py

fig1-fig5 are drawn from the implemented model (DECISION_TABLE, TRANSITIONS, EventType). fig6a/fig6b re-fit the A1 reference
and the configuration selected in results/tuning/standard/summary.json and show the held-out split descriptively (no selection).
"""
from __future__ import annotations

import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

from trustgate import DECISION_TABLE, TRANSITIONS, DecisionType, ExternalSideEffect, RiskBand
from tune_config import A1_CONFIG, DATA_PATH, SEED, TEST_SIZE, build_pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "figures")
DPI = 200

RED, GREEN, AMBER, BLUE, GREY = "#c0392b", "#2e8b57", "#d68910", "#2471a3", "#566573"
FILL = {"untrusted": "#fdecea", "trusted": "#e8f6ef", "advisory": "#fef5e7", "external": "#eef1f4", "neutral": "#f7f9fb",
        "ALLOW": "#d5f0e0", "REVIEW": "#fdebc8", "BLOCK": "#f9d0cc"}


def canvas(w: float, h: float, title: str):
    fig, ax = plt.subplots(figsize=(w * 0.9, h * 0.9))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left", pad=10)
    return fig, ax


def box(ax, x, y, w, h, text, fc="#f7f9fb", ec="#333", lw=1.5, ls="-", fs=8.5, bold=False, double=False, color="black"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12", fc=fc, ec=ec, lw=lw, ls=ls, zorder=2))
    if double:
        ax.add_patch(FancyBboxPatch((x + 0.09, y + 0.09), w - 0.18, h - 0.18, boxstyle="round,pad=0,rounding_size=0.08",
                                    fc="none", ec=ec, lw=lw * 0.8, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal",
            zorder=3, color=color, linespacing=1.25)
    return (x, y, w, h)


def pt(b, side: str, frac: float = 0.5):
    x, y, w, h = b
    return {"l": (x, y + h * frac), "r": (x + w, y + h * frac), "t": (x + w * frac, y + h), "b": (x + w * frac, y)}[side]


def arrow(ax, a, b, text="", color="#333", ls="-", rad=0.0, fs=7.5, lw=1.4, off=(0.0, 0.14), tc=None, ha="center"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", zorder=1.5, shrinkA=1, shrinkB=1))
    if text:
        mx, my = (a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1]
        ax.text(mx, my, text, fontsize=fs, ha=ha, va="center", color=tc or color, zorder=4,
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))


def zone(ax, x, y, w, h, label, ec, fc="none", ls="--"):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=2, ls=ls, zorder=0.5))
    ax.text(x + 0.15, y + h - 0.2, label, fontsize=9, fontweight="bold", color=ec, va="top", zorder=1)


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", os.path.relpath(path, ROOT))


# ------------------------------------------------------------------------------------------------ Figure 1
def fig1_context():
    fig, ax = canvas(17, 10.2, "Figure 1. AI Trust Layer: system context and trust boundary")
    zone(ax, 0.2, 0.9, 4.6, 8.6, "OUTSIDE: UNTRUSTED INPUT", RED, "#fffafa")
    zone(ax, 5.5, 0.9, 6.6, 8.6, "TRUST GATE DOMAIN", GREEN, "#fbfefc")
    zone(ax, 12.8, 0.9, 4.0, 8.6, "OUTSIDE: UNTRUSTED OUTCOME", GREY, "#fafafa")

    user = box(ax, 0.8, 7.4, 3.2, 1.1, "User / requester\n(text is untrusted)", FILL["untrusted"], RED, bold=True)
    agent = box(ax, 0.8, 4.9, 3.2, 1.6, "AI agent / AI system\nproposes actions\n(text, tool name, args)", FILL["untrusted"], RED, bold=True)
    rev = box(ax, 0.8, 1.4, 3.2, 1.7, "Human reviewer\n(simulated)\ntrusted only if listed\nin policy; no authentication", FILL["advisory"], AMBER, bold=True)

    norm = box(ax, 5.8, 7.5, 2.7, 1.1, "Action normalizer\n& validator", FILL["trusted"], GREEN, bold=True)
    pol = box(ax, 9.3, 7.5, 2.5, 1.1, "Policy configuration\nversioned, immutable", FILL["trusted"], GREEN, bold=True, fs=8)
    ra = box(ax, 5.8, 5.4, 2.7, 1.5, "Risk assessor (port)\nA1: TF-IDF+lexicon\n+LogReg. ADVISORY", FILL["advisory"], AMBER, bold=True, fs=8)
    pe = box(ax, 9.3, 5.4, 2.5, 1.5, "Policy evaluation\ndecision table\nAUTHORITY", FILL["trusted"], GREEN, bold=True, fs=8)
    life = box(ax, 5.8, 3.7, 6.0, 1.3, "AgentAction lifecycle (11 states)\ninvariants INV-01..06; only the gate sets AUTHORIZED", FILL["trusted"], GREEN, bold=True, fs=8.3)
    appr = box(ax, 5.8, 1.4, 2.7, 1.7, "Approval request\nPENDING ->\nGRANTED / REJECTED", FILL["trusted"], GREEN, bold=True, fs=8)
    aud = box(ax, 9.3, 1.4, 2.5, 1.7, "Audit store\nappend-only;\ntext digest only", FILL["trusted"], GREEN, bold=True, fs=8)

    tool = box(ax, 13.3, 4.1, 3.0, 1.5, "Tool (simulated)\noutcome not trusted", FILL["external"], GREY, bold=True)
    ext = box(ax, 13.3, 1.7, 3.0, 1.5, "External system /\nthird-party service\n(not modelled)", FILL["external"], GREY, bold=True)

    arrow(ax, pt(user, "b"), pt(agent, "t"), "request text")
    arrow(ax, pt(agent, "r", 0.85), pt(norm, "l", 0.4), "proposed\naction", off=(-0.15, 0.55), fs=7.2)
    arrow(ax, pt(norm, "b"), pt(ra, "t"), "normalized text", off=(0.0, 0.0), fs=7)
    arrow(ax, pt(ra, "r"), pt(pe, "l"), "", lw=1.4)
    ax.text(8.9, 6.45, "score\nor none", fontsize=6.8, ha="center", va="center", color="#333", zorder=4)
    arrow(ax, pt(pol, "b"), pt(pe, "t"), "", lw=1.4)
    ax.text(10.75, 7.2, "thresholds,\nregistry", fontsize=6.6, ha="left", va="center", color="#333", zorder=4)
    arrow(ax, pt(pe, "b", 0.5), pt(life, "t", 0.8), "decision", off=(0.75, 0.0), fs=7.2)
    arrow(ax, pt(life, "b", 0.25), pt(appr, "t", 0.5), "REVIEW only", off=(-0.2, 0.0), fs=7)
    arrow(ax, pt(life, "b", 0.8), pt(aud, "t", 0.5), "every event", off=(0.85, 0.0), fs=7)
    arrow(ax, pt(appr, "l", 0.7), pt(rev, "r", 0.7), "", color=AMBER)
    arrow(ax, pt(rev, "r", 0.3), pt(appr, "l", 0.3), "", color=AMBER)
    ax.text(5.15, 2.6, "ask /\ngrant or\nreject", fontsize=6.6, ha="center", va="center", color=AMBER, zorder=4, bbox=dict(fc="white", ec="none", pad=0.8, alpha=0.95))
    arrow(ax, pt(life, "r", 0.7), pt(tool, "l", 0.8), "", color=GREEN)
    ax.text(12.45, 5.45, "execute only\nif AUTHORIZED", fontsize=6.6, ha="center", va="center", color=GREEN, zorder=4, bbox=dict(fc="white", ec="none", pad=0.8, alpha=0.95))
    arrow(ax, pt(tool, "l", 0.25), pt(life, "r", 0.3), "", color=GREY, ls="--")
    ax.text(12.45, 3.55, "completed /\nfailed", fontsize=6.6, ha="center", va="center", color=GREY, zorder=4, bbox=dict(fc="white", ec="none", pad=0.8, alpha=0.95))
    arrow(ax, pt(tool, "b"), pt(ext, "t"), "side effects", fs=7)

    ax.text(0.2, 0.4, "Legend:", fontsize=8.5, fontweight="bold", va="center")
    for i, (lab, ec, fc) in enumerate([("untrusted", RED, FILL["untrusted"]), ("trusted authority", GREEN, FILL["trusted"]),
                                       ("advisory / conditional", AMBER, FILL["advisory"]), ("outside, outcome untrusted", GREY, FILL["external"])]):
        x0 = 1.8 + i * 3.9
        ax.add_patch(Rectangle((x0, 0.25), 0.45, 0.3, fc=fc, ec=ec, lw=1.5))
        ax.text(x0 + 0.6, 0.4, lab, fontsize=8, va="center")
    save(fig, "fig1_system_context.png")


# ------------------------------------------------------------------------------------------------ Figure 2
def fig2_workflow():
    fig, ax = canvas(21.4, 8.6, "Figure 2. Agent action trust-evaluation workflow")
    names = ["1. Request", "2. Action proposal", "3. Normalization", "4. Risk assessment", "5. Policy evaluation"]
    events = ["(outside)", "ActionProposed", "ActionNormalized", "RiskAssessed", "(pure function, no event)"]
    states = ["", "state: PROPOSED", "state: NORMALIZED", "state: RISK_ASSESSED", ""]
    fills = [FILL["untrusted"], FILL["neutral"], FILL["neutral"], FILL["advisory"], FILL["trusted"]]
    top = []
    for i, (n, e, s_, f) in enumerate(zip(names, events, states, fills)):
        b = box(ax, 0.4 + i * 3.45, 6.0, 2.75, 1.7, "", f, GREEN if i == 4 else GREY)
        top.append(b)
        ax.text(b[0] + b[2] / 2, b[1] + 1.25, n, fontsize=9, fontweight="bold", ha="center", va="center", zorder=3)
        ax.text(b[0] + b[2] / 2, b[1] + 0.8, e, fontsize=7.6, ha="center", va="center", color=BLUE, style="italic", zorder=3)
        ax.text(b[0] + b[2] / 2, b[1] + 0.38, s_, fontsize=7.2, ha="center", va="center", color=GREY, zorder=3)
        if i:
            arrow(ax, pt(top[i - 1], "r"), pt(b, "l"))
    dx, dy = 19.0, 6.85
    ax.add_patch(Polygon([(dx, dy + 0.95), (dx + 1.9, dy), (dx, dy - 0.95), (dx - 1.9, dy)], fc="#fffdf5", ec=AMBER, lw=1.8, zorder=2))
    ax.text(dx, dy, "6. Decision\nALLOW / REVIEW\n/ BLOCK", ha="center", va="center", fontsize=8, fontweight="bold", zorder=3)
    arrow(ax, pt(top[4], "r"), (dx - 1.9, dy))

    allow = box(ax, 8.2, 3.5, 3.3, 1.1, "ALLOW\nevent: ActionAllowed\nstate: ALLOWED (authorized)", FILL["ALLOW"], GREEN, fs=8)
    rev = box(ax, 12.5, 3.5, 3.6, 1.1, "REVIEW\nevent: HumanApprovalRequested\nstate: PENDING_APPROVAL", FILL["REVIEW"], AMBER, fs=8)
    blk = box(ax, 17.1, 3.5, 3.3, 1.1, "BLOCK\nevent: ActionBlocked\nstate: BLOCKED (terminal)", FILL["BLOCK"], RED, fs=8)
    arrow(ax, (dx - 0.15, dy - 0.93), pt(allow, "t", 0.5), "ALLOW", color=GREEN, off=(-1.5, 0.12))
    arrow(ax, (dx + 0.25, dy - 0.9), pt(rev, "t", 0.5), "REVIEW", color=AMBER, off=(-0.5, 0.2))
    arrow(ax, (dx + 0.8, dy - 0.62), pt(blk, "t", 0.5), "BLOCK", color=RED, off=(0.55, 0.15))

    human = box(ax, 12.5, 1.6, 3.6, 1.1, "Human reviewer decides\n(simulated, listed in policy)", FILL["advisory"], AMBER, fs=8, bold=True)
    term = box(ax, 17.1, 1.6, 3.3, 1.1, "BLOCKED / REJECTED\nterminal: nothing executes", FILL["BLOCK"], RED, fs=8, bold=True, double=True)
    execb = box(ax, 8.2, 1.6, 3.3, 1.1, "7. Execution (simulated)\nToolExecutionStarted\n(audit written first)", FILL["ALLOW"], GREEN, fs=8, bold=True)
    done = box(ax, 3.9, 1.6, 3.4, 1.1, "EXECUTED / EXECUTION_FAILED\nToolExecutionCompleted /\nToolExecutionFailed", FILL["external"], GREY, fs=7.6, bold=True, double=True)
    arrow(ax, pt(allow, "b"), pt(execb, "t"))
    arrow(ax, pt(rev, "b"), pt(human, "t"))
    arrow(ax, pt(blk, "b"), pt(term, "t"))
    arrow(ax, pt(human, "l"), pt(execb, "r"), "granted", color=GREEN, off=(0, 0.2), fs=7.2)
    arrow(ax, pt(human, "r"), pt(term, "l"), "rejected", color=RED, off=(0, 0.2), fs=7.2)
    arrow(ax, pt(execb, "l"), pt(done, "r"))

    aud = box(ax, 0.4, 0.2, 20.0, 0.75, "8. Audit recording: AuditRecorded after EVERY event above (INV-05). Records hold ids, states, decision, rule id, score, versions, text digest; never the text.",
              FILL["trusted"], GREEN, fs=8.3, bold=True)
    for xx in (5.6, 9.85, 14.3, 18.75):
        ax.plot([xx, xx], [aud[1] + aud[3], 1.6], color=GREEN, lw=0.8, ls=":", zorder=0.4)

    ax.add_patch(Rectangle((0.4, 2.7), 3.2, 2.5, fc="white", ec="#999", lw=1))
    ax.text(0.55, 5.05, "Legend", fontsize=8.5, fontweight="bold", va="top")
    ax.add_patch(Rectangle((0.6, 4.3), 0.45, 0.28, fc=FILL["neutral"], ec=GREY)); ax.text(1.2, 4.44, "action (box)", fontsize=7.8, va="center")
    ax.text(0.6, 3.95, "blue italic = event", fontsize=7.8, color=BLUE, style="italic", va="center")
    ax.text(0.6, 3.6, "grey text = state", fontsize=7.8, color=GREY, va="center")
    ax.add_patch(Polygon([(0.82, 3.35), (1.05, 3.2), (0.82, 3.05), (0.59, 3.2)], fc="#fffdf5", ec=AMBER)); ax.text(1.2, 3.2, "decision (value)", fontsize=7.8, va="center")
    save(fig, "fig2_trust_evaluation_workflow.png")


# ------------------------------------------------------------------------------------------------ Figure 3
def fig3_states():
    fig, ax = canvas(18.4, 10.6, "Figure 3. AgentAction state-transition diagram")
    W, H = 2.8, 0.95
    pos = {
        "PROPOSED": (0.4, 9.0), "NORMALIZED": (4.6, 9.0), "RISK_ASSESSED": (8.8, 9.0),
        "ALLOWED": (2.0, 6.6), "PENDING_APPROVAL": (7.4, 6.6), "BLOCKED": (12.6, 6.6),
        "APPROVED": (5.4, 4.2), "REJECTED": (10.4, 4.2),
        "EXECUTING": (2.0, 2.0),
        "EXECUTED": (0.3, 0.2), "EXECUTION_FAILED": (4.6, 0.2),
    }
    terminal = {"BLOCKED": RED, "REJECTED": RED, "EXECUTED": GREEN, "EXECUTION_FAILED": GREY}
    fills = {"ALLOWED": FILL["ALLOW"], "PENDING_APPROVAL": FILL["REVIEW"], "BLOCKED": FILL["BLOCK"], "APPROVED": FILL["ALLOW"],
             "REJECTED": FILL["BLOCK"], "EXECUTED": FILL["ALLOW"], "EXECUTION_FAILED": FILL["external"]}
    nodes = {n: box(ax, x, y, W, H, n, fills.get(n, FILL["neutral"]), terminal.get(n, "#333"), bold=True, fs=9, double=n in terminal, lw=1.8)
             for n, (x, y) in pos.items()}
    ax.text(0.4, 10.4, "Evaluation phase = PROPOSED -> NORMALIZED -> RISK_ASSESSED (these replace the sketch's single 'EVALUATING' state).", fontsize=8, color=GREY, va="center")

    sides = {("PROPOSED", "NORMALIZED"): ("r", "l"), ("NORMALIZED", "RISK_ASSESSED"): ("r", "l"),
             ("RISK_ASSESSED", "ALLOWED"): ("b", "t"), ("RISK_ASSESSED", "PENDING_APPROVAL"): ("b", "t"), ("RISK_ASSESSED", "BLOCKED"): ("b", "t"),
             ("PENDING_APPROVAL", "APPROVED"): ("b", "t"), ("PENDING_APPROVAL", "REJECTED"): ("b", "t"),
             ("ALLOWED", "EXECUTING"): ("b", "t"), ("APPROVED", "EXECUTING"): ("b", "r"),
             ("EXECUTING", "EXECUTED"): ("b", "t"), ("EXECUTING", "EXECUTION_FAILED"): ("b", "t")}
    fr = {("RISK_ASSESSED", "ALLOWED"): ((0.2, 0.7)), ("RISK_ASSESSED", "PENDING_APPROVAL"): (0.5, 0.6), ("RISK_ASSESSED", "BLOCKED"): (0.85, 0.3),
          ("PENDING_APPROVAL", "APPROVED"): (0.25, 0.7), ("PENDING_APPROVAL", "REJECTED"): (0.75, 0.3),
          ("APPROVED", "EXECUTING"): (0.3, 0.6), ("EXECUTING", "EXECUTED"): (0.3, 0.6), ("EXECUTING", "EXECUTION_FAILED"): (0.7, 0.4)}
    offs = {("RISK_ASSESSED", "ALLOWED"): (-0.4, 0.45), ("RISK_ASSESSED", "PENDING_APPROVAL"): (-1.55, 0.0), ("RISK_ASSESSED", "BLOCKED"): (1.7, 0.2),
            ("PENDING_APPROVAL", "APPROVED"): (-1.5, 0.0), ("PENDING_APPROVAL", "REJECTED"): (1.55, 0.0),
            ("ALLOWED", "EXECUTING"): (-1.15, 0.0), ("APPROVED", "EXECUTING"): (1.4, 0.0),
            ("EXECUTING", "EXECUTED"): (-1.2, 0.0), ("EXECUTING", "EXECUTION_FAILED"): (1.3, 0.0)}
    for (state, event), nxt in TRANSITIONS.items():
        (target,) = tuple(nxt)
        a_side, b_side = sides[(state.value, target.value)]
        fa, fb = fr.get((state.value, target.value), (0.5, 0.5))
        arrow(ax, pt(nodes[state.value], a_side, fa), pt(nodes[target.value], b_side, fb), event.value, color=GREEN, fs=7.2,
              off=offs.get((state.value, target.value), (0, 0.3)), lw=1.5)

    arrow(ax, pt(nodes["BLOCKED"], "b", 0.25), pt(nodes["EXECUTING"], "r", 0.25), "X BLOCKED -> EXECUTING (INV-01)", color=RED, ls="--", rad=-0.25, fs=7.4, off=(2.4, -1.5), lw=1.5)

    ax.add_patch(Rectangle((13.7, 0.1), 4.6, 5.8, fc="white", ec="#999", lw=1))
    lines = [("Legend", True, "black"), ("green arrow = valid transition (event label)", False, GREEN),
             ("red dashed = a forbidden transition (example)", False, RED), ("double border = terminal state", False, "black"), ("", False, "black"),
             ("Tested exhaustively (11 states x 10 events):", True, "black"), (f"{len(TRANSITIONS)} valid (state, event) pairs", False, GREEN),
             (f"{11 * 10 - len(TRANSITIONS)} forbidden pairs raise InvalidTransitionError", False, RED), ("", False, "black"),
             ("Also forbidden (not drawn):", True, "black"), ("PENDING_APPROVAL -> EXECUTING (INV-02)", False, RED),
             ("EXECUTED -> EXECUTING, repeat run (INV-06)", False, RED), ("NORMALIZED -> ALLOWED, skips risk step", False, RED),
             ("any event after a terminal state", False, RED), ("", False, "black"),
             ("Guards: AUTHORIZED needed to execute;", False, "black"), ("reviewer must be listed in policy;", False, "black")]
    for i, (t, b, c) in enumerate(lines):
        ax.text(13.85, 5.7 - i * 0.318, t, fontsize=7.6, fontweight="bold" if b else "normal", color=c, va="top")
    save(fig, "fig3_agentaction_state_transitions.png")


# ------------------------------------------------------------------------------------------------ Figure 4
def fig4_decision_matrix():
    fig = plt.figure(figsize=(12.5, 6.8))
    ax = fig.add_axes([0.12, 0.08, 0.50, 0.66])
    bands = [RiskBand.UNKNOWN, RiskBand.HIGH, RiskBand.MEDIUM, RiskBand.LOW]
    effects = [ExternalSideEffect.NO, ExternalSideEffect.YES, ExternalSideEffect.UNKNOWN]
    col = {DecisionType.ALLOW: FILL["ALLOW"], DecisionType.REVIEW: FILL["REVIEW"], DecisionType.BLOCK: FILL["BLOCK"]}
    edge = {DecisionType.ALLOW: GREEN, DecisionType.REVIEW: AMBER, DecisionType.BLOCK: RED}
    for r, b in enumerate(bands):
        for c, e in enumerate(effects):
            rule, dec = DECISION_TABLE[(b, e)]
            ax.add_patch(Rectangle((c, len(bands) - 1 - r), 1, 1, fc=col[dec], ec="white", lw=3))
            ax.text(c + 0.5, len(bands) - 1 - r + 0.58, dec.value, ha="center", va="center", fontsize=15, fontweight="bold", color=edge[dec])
            ax.text(c + 0.5, len(bands) - 1 - r + 0.25, rule, ha="center", va="center", fontsize=9, color=GREY)
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 4)
    ax.set_xticks([0.5, 1.5, 2.5])
    ax.set_xticklabels(["NO", "YES", "UNKNOWN\n(unregistered tool;\ntreated like YES)"], fontsize=10)
    ax.xaxis.tick_top()
    ax.set_xlabel("External side effect (authority: policy tool registry, never the agent)", fontsize=10, labelpad=8)
    ax.xaxis.set_label_position("top")
    ax.set_yticks([3.5, 2.5, 1.5, 0.5])
    ax.set_yticklabels(["UNKNOWN\n(no score: fail closed)", "HIGH\n(score > 0.50)", "MEDIUM\n(0.35 <= score <= 0.50)", "LOW\n(score < 0.35)"], fontsize=9.5)
    ax.set_ylabel("Risk band (from the risk score)", fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.suptitle("Figure 4. Three-class trust decision matrix (the implemented rule, 12 rows)", x=0.02, y=0.98, ha="left", fontsize=14, fontweight="bold")

    side = fig.add_axes([0.66, 0.08, 0.33, 0.66])
    side.axis("off")
    txt = [("Conditions of the rule", True, "black"),
           ("Risk band: A1 evidence for 0.50 (the logistic-", False, "black"), ("regression label boundary); 0.35 is a", False, "black"),
           ("PROJECT DESIGN DECISION (untuned).", False, "black"),
           ("External side effect: A2 design extension.", False, "black"), ("", False, "black"),
           ("Evaluated but NOT in the rule", True, "black"),
           ("authorization: an OUTPUT of the gate", False, GREY), ("(set after ALLOW or a granted approval),", False, GREY), ("not an input condition.", False, GREY),
           ("data sensitivity, reversibility, privilege:", False, GREY), ("deferred - no A1 evidence, no data source.", False, GREY), ("", False, "black"),
           ("Default / missing values", True, "black"),
           ("no risk score -> BLOCK (fail closed)", False, RED), ("unknown tool -> never ALLOW", False, AMBER), ("", False, "black"),
           ("Verified: table parsed from decision_table.md", False, GREEN), ("equals code; oracle on 107 scores x 3.", False, GREEN)]
    for i, (t, b, c) in enumerate(txt):
        side.text(0, 1 - i * 0.052, t, fontsize=9, fontweight="bold" if b else "normal", color=c, va="top")
    save(fig, "fig4_decision_matrix.png")


# ------------------------------------------------------------------------------------------------ Figure 5
def fig5_architecture():
    fig, ax = canvas(17, 11.4, "Figure 5. AI Trust Layer: defense-in-depth architecture")
    cx, w = 4.2, 5.4
    L1 = box(ax, cx, 9.2, w, 1.1, "Layer 1  Action normalizer & validator\nshape, identifiers, tool name, NFC text", FILL["trusted"], GREEN, bold=True, fs=8.5)
    L2 = box(ax, cx, 7.3, w, 1.3, "Layer 2  Feature extraction + FAST risk classifier\nA1: TF-IDF + intent/framing lexicon + LogReg\nscore in [0,1] (advisory)", FILL["advisory"], AMBER, bold=True, fs=8.5)
    L3 = box(ax, cx, 5.0, w, 1.3, "Layer 3  Policy engine (decision table, versioned)\nthe only authority for ALLOW / REVIEW / BLOCK", FILL["trusted"], GREEN, bold=True, fs=8.5)
    opt = box(ax, 10.7, 7.1, 5.5, 1.7, "OPTIONAL (not implemented)\nStronger safety model for uncertain cases\n(MEDIUM band only). Sentence embeddings or an\nLLM judge; A1 non-goal today", "#f4f4f4", GREY, bold=False, fs=8, ls="--")
    agent = box(ax, cx + 0.6, 10.75, w - 1.2, 0.5, "AI agent / AI system (untrusted proposer)", FILL["untrusted"], RED, bold=True, fs=8.5)
    allow = box(ax, 0.5, 3.0, 4.2, 1.1, "ALLOW -> Tool execution\n(simulated; only if AUTHORIZED)", FILL["ALLOW"], GREEN, bold=True, fs=8.3)
    review = box(ax, 5.4, 3.0, 4.2, 1.1, "REVIEW -> Layer 4  Human approval\nlisted reviewer, decided once", FILL["REVIEW"], AMBER, bold=True, fs=8.3)
    block = box(ax, 10.3, 3.0, 4.2, 1.1, "BLOCK -> stop (terminal)\nnothing is executed", FILL["BLOCK"], RED, bold=True, fs=8.3)
    L5 = box(ax, 0.5, 0.9, 14.0, 1.2, "Layer 5  Audit layer: append-only record of every event (INV-05), written BEFORE execution.\nDecision, rule id, score, policy and model versions, text digest; never the request text.",
             FILL["trusted"], GREEN, bold=True, fs=8.5)

    arrow(ax, pt(agent, "b"), pt(L1, "t", 0.5), "proposed action")
    arrow(ax, pt(L1, "b"), pt(L2, "t"), "normalized text only")
    arrow(ax, pt(L2, "b"), pt(L3, "t"), "risk score or none")
    arrow(ax, pt(L2, "r", 0.5), pt(opt, "l", 0.5), "uncertain", ls="--", color=GREY, off=(0, 0.2))
    arrow(ax, pt(opt, "b", 0.15), pt(L3, "r", 0.7), "second opinion", ls="--", color=GREY, rad=0.0, off=(0.9, -0.3))
    arrow(ax, pt(L3, "b", 0.15), pt(allow, "t"), "", color=GREEN)
    arrow(ax, pt(L3, "b", 0.5), pt(review, "t"), "", color=AMBER)
    arrow(ax, pt(L3, "b", 0.85), pt(block, "t"), "", color=RED)
    for b_ in (allow, review, block):
        arrow(ax, pt(b_, "b"), (b_[0] + b_[2] / 2, 2.1), "", color=GREEN, ls=":", lw=1)
    box(ax, 10.7, 9.2, 5.5, 1.5, "Replaceable by design\nPorts: RiskAssessor, ToolExecutor, AuditStore, Clock.\nSwap the classifier or store without touching\nthe rules (domain imports only the stdlib).",
        FILL["neutral"], BLUE, fs=8)
    ax.add_patch(Rectangle((0.5, 10.4 - 0.2 - 0.0), 0.0, 0.0))
    ax.text(0.5, 6.4, "Defense in depth: no single\nlayer can authorize execution.\nAUTHORIZED comes only from\nLayer 3 (ALLOW) or Layer 4 (grant).", fontsize=8.5, color=GREEN, va="center", fontweight="bold")
    ax.text(0.5, 0.35, "solid = implemented in A2; dashed = optional / future (not implemented)", fontsize=8.5, color=GREY)
    save(fig, "fig5_defense_in_depth_architecture.png")


# ------------------------------------------------------------------------------------------------ Figure 6 (data)
def model_scores() -> dict[str, Any]:
    df = pd.read_csv(DATA_PATH)
    tr, te = train_test_split(df, test_size=TEST_SIZE, random_state=SEED, stratify=df["label"])
    with open(os.path.join(ROOT, "results", "tuning", "standard", "summary.json"), encoding="utf-8") as f:
        selected = json.load(f)["best_config"]
    out: dict[str, Any] = {"selected_cfg": selected}
    for name, cfg in (("A1 reference", A1_CONFIG), ("Selected config", selected)):
        model = build_pipeline(cfg).fit(tr["text"], tr["label"])
        k = list(model.classes_).index("harmful")
        p_te = model.predict_proba(te["text"])[:, k]
        p_oof = cross_val_predict(build_pipeline(cfg), tr["text"], tr["label"], cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
                                  method="predict_proba")[:, k]
        out[name] = {"p_te": p_te, "y_te": (te["label"] == "harmful").to_numpy(), "p_oof": p_oof, "y_tr": (tr["label"] == "harmful").to_numpy()}
    return out


def binary_metrics(p: np.ndarray, y: np.ndarray, cut: float, inclusive: bool = False) -> dict[str, float]:
    pred = (p >= cut) if inclusive else (p > cut)
    tp, fp, fn, tn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum()), int((~pred & ~y).sum())
    rec = tp / (tp + fn)
    prec = tp / (tp + fp) if tp + fp else 0.0
    spec = tn / (tn + fp)
    f2 = 5 * prec * rec / (4 * prec + rec) if prec + rec else 0.0
    return {"Recall\n(harmful caught)": rec, "Precision": prec, "Specificity\n(benign allowed)": spec,
            "Accuracy": (tp + tn) / len(y), "F2 score\n(recall-weighted)": f2, "ROC-AUC": float(roc_auc_score(y, p))}


def fig6a_radar(sc):
    series = [
        ("A1 reference, flag if score > 0.50", sc["A1 reference"], 0.50, False, "#7f8c8d"),
        ("Selected config, flag if score > 0.50", sc["Selected config"], 0.50, False, BLUE),
        ("Selected config, flag if score >= 0.15 (REVIEW or BLOCK)", sc["Selected config"], 0.15, True, RED),
    ]
    rows = [(lab, binary_metrics(d["p_te"], d["y_te"], cut, inc), col) for lab, d, cut, inc, col in series]
    axes_names = list(rows[0][1])
    ang = np.linspace(0, 2 * np.pi, len(axes_names), endpoint=False).tolist()
    fig = plt.figure(figsize=(11.5, 8.2))
    ax = fig.add_axes([0.04, 0.08, 0.58, 0.78], polar=True)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    for lab, m, col in rows:
        v = list(m.values())
        ax.plot(ang + ang[:1], v + v[:1], color=col, lw=2.4 if col != "#7f8c8d" else 2, label=lab)
        ax.fill(ang + ang[:1], v + v[:1], color=col, alpha=0.10)
    ax.set_xticks(ang)
    ax.set_xticklabels(axes_names, fontsize=10)
    ax.get_xticklabels()[0].set_fontweight("bold")
    ax.get_xticklabels()[0].set_color(RED)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=8, color=GREY)
    ax.plot(np.linspace(0, 2 * np.pi, 200), [0.8] * 200, color=GREEN, lw=1, ls=":")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.02), fontsize=9, frameon=False)
    fig.suptitle("Figure 6a. Performance profile on the held-out test split (n = 40; 20 harmful, 20 benign)", x=0.04, ha="left", fontsize=13, fontweight="bold")

    tab = fig.add_axes([0.64, 0.06, 0.35, 0.80])
    tab.axis("off")
    tab.set_xlim(0, 1)
    tab.set_ylim(0, 1)
    tab.text(0, 0.99, "Values", fontsize=10, fontweight="bold", va="top")
    for i, (lab, m, col) in enumerate(rows):
        top = 0.94 - i * 0.275
        tab.text(0, top, lab.replace(", flag", "\nflag"), fontsize=8.2, color=col, fontweight="bold", va="top")
        for j, (k, v) in enumerate(m.items()):
            tab.text(0.03, top - 0.085 - j * 0.026, f"{k.split(chr(10))[0]:<12}{v:.3f}", fontsize=7.8, va="top", family="monospace")
    tab.text(0, 0.0, "Dotted ring = 0.80. Recall is the A1 priority (a missed\nharmful request is the severe error), but read it with\nspecificity: flagging everything gives recall 1.0 and\nspecificity 0. 20 harmful rows: recall moves in steps\nof 0.05; intervals are wide (19/20 -> 0.76 to 0.99).", fontsize=7.6, color=GREY, va="bottom")
    save(fig, "fig6a_radar_performance.png")


def fig6b_roc(sc):
    fig, axs = plt.subplots(1, 2, figsize=(12.5, 5.9))
    spec = [("A1 reference", "#7f8c8d"), ("Selected config", BLUE)]
    for ax, key, ykey, title in ((axs[0], "p_te", "y_te", "Held-out test split (n = 40, descriptive)"),
                                 (axs[1], "p_oof", "y_tr", "Out-of-fold, training split (n = 160)")):
        for name, col in spec:
            d = sc[name]
            fpr, tpr, thr = roc_curve(d[ykey], d[key])
            ax.plot(fpr, tpr, color=col, lw=2.2, label=f"{name} (AUC {roc_auc_score(d[ykey], d[key]):.3f})")
        for cut, mk, lab in ((0.50, "o", "cutoff 0.50"), (0.15, "s", "cutoff 0.15")):
            d = sc["Selected config"]
            y, p = d[ykey], d[key]
            pred = p >= cut if cut < 0.5 else p > cut
            ax.scatter((pred & ~y).sum() / (~y).sum(), (pred & y).sum() / y.sum(), marker=mk, s=70, color=BLUE, edgecolor="black", zorder=5)
            ax.annotate(f"{lab}\nrecall {(pred & y).sum() / y.sum():.2f}, FPR {(pred & ~y).sum() / (~y).sum():.2f}",
                        ((pred & ~y).sum() / (~y).sum(), (pred & y).sum() / y.sum()), textcoords="offset points", xytext=(10, -34) if cut > 0.3 else (-100, -36), fontsize=7.8)
        ax.plot([0, 1], [0, 1], ls="--", color="#aaa", lw=1, label="chance")
        ax.axhline(0.8, color=GREEN, lw=0.8, ls=":")
        ax.set_xlabel("False-positive rate (benign requests flagged)")
        ax.set_ylabel("True-positive rate = recall (harmful caught)")
        ax.set_title(title, fontsize=10.5)
        ax.set_xlim(-0.01, 1.01)
        ax.set_ylim(0, 1.03)
        ax.grid(alpha=0.25)
        ax.legend(loc="lower right", fontsize=8.5)
    fig.suptitle("Figure 6b. ROC curves: A1 reference vs. selected configuration", x=0.06, ha="left", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "fig6b_roc_curves.png")


def main() -> None:
    fig1_context()
    fig2_workflow()
    fig3_states()
    fig4_decision_matrix()
    fig5_architecture()
    sc = model_scores()
    fig6a_radar(sc)
    fig6b_roc(sc)


if __name__ == "__main__":
    main()
