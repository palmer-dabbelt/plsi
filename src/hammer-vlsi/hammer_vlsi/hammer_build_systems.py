#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  hammer_build_systems.py
#  Class containing all the methods to create VLSI flow build system infrastructure
#
#  See LICENSE for licence details.

from .driver import HammerDriver

import os
import sys
import textwrap
from typing import List, Dict, Tuple, Callable

def build_noop(driver: HammerDriver, append_error_func: Callable[[str], None]) -> dict:
    """
    Do nothing, just return the dependency graph.

    :param driver: The HammerDriver
    :return: The dependency graph
    """
    dependency_graph = driver.get_hierarchical_dependency_graph()
    return dependency_graph


def build_makefile(driver: HammerDriver, append_error_func: Callable[[str], None]) -> dict:
    """
    Build a Makefile include in the obj_dir called hammer.d. This is intended to be dynamically
    created and included into a top-level Makefile.

    The Makefile will contain targets for the following hammer actions, as well as any necessary
    bridge actions (xyz-to-abc):
        - pcb
        - syn
        - par
        - drc
        - lvs
        - sim-rtl
        - sim-syn
        - sim-par
        - power-par

    For hierarchical flows, the syn, par, drc, lvs, sim, and power actions will all be suffixed with the name
    of the hierarchical modules (e.g. syn-Top, syn-SubModA, par-SubModA, etc.). The appropriate
    dependencies and bridge actions are automatically generated from the hierarchy provided in the
    Hammer IR.

    For actions that can be run at multiple points in the flow such as sim, the name of the target
    will include the action it is being run after (e.g. sim-syn, sim-par, etc.). With no suffix
    an rtl level simulation will be run.

    Additionally, "redo" steps are created (e.g. redo-par for flat designs or redo-par-Top for
    hierarchical), which allow the user to bypass the normal Makefile dependencies and force a
    rerun of a particular task. This is useful when the user wants to change an input Hammer IR file
    knowing it will not affect intermediate steps in the design.

    An example use case for integrating this file into a top flow is provided below. Be sure to use
    real tabs if copying this snippet!

    ```
    TOP ?= MyTop
    OBJ_DIR ?= $(abspath build-$(TOP))
    INPUT_CONFS ?= foo.yaml bar.yaml baz.yaml

    HAMMER_EXEC ?= ./mychip-vlsi.py

    .PHONY: all
    all: drc-$(TOP) lvs-$(TOP)

    GENERATED_CONF = $(OBJ_DIR)/input.yaml

    $(GENERATED_CONF):
        echo "synthesis.inputs.top_module: $(TOP)" > $@
        echo "pcb.inputs.top_module: $(TOP)" >> $@

    $(OBJ_DIR)/hammer.d: $(GENERATED_CONF)
        $(HAMMER_EXEC) -e env.yaml $(foreach x,$(INPUT_CONFS) $(GENERATED_CONF), -p $(x)) --obj_dir $(OBJ_DIR) build

    include $(OBJ_DIR)/hammer.d
    ```

    The generated Makefile has a few variables that are set if absent. This allows the user to override them without
    modifying hammer.d. They are listed as follows:
        - HAMMER_EXEC: This sets the actual python executable containing the HammerDriver main() function. It is set to
          the executable used to generate the Makefile by default.
        - HAMMER_DEPENDENCIES: The list of dependences to use for the initial syn and pcb targets. It is set to the set
          of all input configurations, environment settings, and input files by default.
        - HAMMER_*_DEPENDENCIES: There is a version of this variable for each action. It allows the user to have more
          fine grained depencies compared to the blunt HAMMER_DEPENDENCIES. It is set as a dependency for the respective
          action. Often used with clearing the global HAMMER_DEPENDENCIES.
        - HAMMER_EXTRA_ARGS: This is passed to the Hammer executable for all targets. This is unset by default.
          Its primary uses are for adding additional configuration files with -p, --to_step/until_step, and/or --from_step/
          after_step options. An example use is "make redo-par-Top HAMMER_EXTRA_ARGS="-p patch.yaml --from_step placement".

    :param driver: The HammerDriver
    :return: The dependency graph
    """
    dependency_graph = driver.get_hierarchical_dependency_graph()
    makefile = os.path.join(driver.obj_dir, "hammer.d")
    default_dependencies = driver.options.project_configs + driver.options.environment_configs
    default_dependencies.extend(list(driver.database.get_setting("synthesis.inputs.input_files", [])))
    # Resolve the canonical path for each dependency
    default_dependencies = [os.path.realpath(x) for x in default_dependencies]
    output = "HAMMER_EXEC ?= {}\n".format(os.path.realpath(sys.argv[0]))
    output += "HAMMER_DEPENDENCIES ?= {}\n\n".format(" ".join(default_dependencies))
    syn_deps = "$(HAMMER_DEPENDENCIES)"
    # Get the confs passed into this execution
    env_confs = " ".join(["-e " + os.path.realpath(x) for x in driver.options.environment_configs])
    proj_confs = " ".join(["-p " + os.path.realpath(x) for x in driver.options.project_configs])
    obj_dir = os.path.realpath(driver.obj_dir)

    # Global steps that are the same for hier or flat
    pcb_run_dir = os.path.join(obj_dir, "pcb-rundir")
    pcb_out = os.path.join(pcb_run_dir, "pcb-output-full.json")
    output += textwrap.dedent("""
        ####################################################################################
        ## Global steps
        ####################################################################################
        .PHONY: pcb
        pcb: {pcb_out}

        {pcb_out}: {syn_deps}
        \t$(HAMMER_EXEC) {env_confs} {all_inputs} --obj_dir {obj_dir} pcb

        """.format(pcb_out=pcb_out, syn_deps=syn_deps, env_confs=env_confs, all_inputs=proj_confs, obj_dir=obj_dir))

    make_text = textwrap.dedent("""
        ####################################################################################
        ## Steps for {mod}
        ####################################################################################
        .PHONY: sim-rtl{suffix} syn{suffix} sim-syn{suffix} par{suffix} sim-par{suffix} power-par{suffix} drc{suffix} lvs{suffix}
        sim-rtl{suffix}: {sim_rtl_out}
        syn{suffix}: {syn_out}
        sim-syn{suffix}: {sim_syn_out}
        par{suffix}: {par_out}
        sim-par{suffix}: {sim_par_out}
        power-par{suffix}: {power_par_out}
        drc{suffix}: {drc_out}
        lvs{suffix}: {lvs_out}

        {par_to_syn}

        {sim_rtl_out}: {syn_deps} $(HAMMER_SIM_RTL_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} {p_sim_rtl_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_rtl_run_dir} --obj_dir {obj_dir} sim{suffix}

        {syn_out}: {syn_deps} $(HAMMER_SYN_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} {p_syn_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} syn{suffix}

        {sim_syn_in}: {syn_out}
        \t$(HAMMER_EXEC) {env_confs} -p {syn_out} $(HAMMER_EXTRA_ARGS) -o {sim_syn_in} --obj_dir {obj_dir} syn-to-sim

        {sim_syn_out}: {sim_syn_in} $(HAMMER_SIM_SYN_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {sim_syn_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_syn_run_dir} --obj_dir {obj_dir} sim{suffix}

        {par_in}: {syn_out}
        \t$(HAMMER_EXEC) {env_confs} -p {syn_out} $(HAMMER_EXTRA_ARGS) -o {par_in} --obj_dir {obj_dir} syn-to-par

        {par_out}: {par_in} $(HAMMER_PAR_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {par_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} par{suffix}

        {sim_par_in}: {par_out}
        \t$(HAMMER_EXEC) {env_confs} -p {par_out} $(HAMMER_EXTRA_ARGS) -o {sim_par_in} --obj_dir {obj_dir} par-to-sim

        {sim_par_out}: {sim_par_in} $(HAMMER_SIM_PAR_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {sim_par_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_par_run_dir} --obj_dir {obj_dir} sim{suffix}

        {power_sim_par_in}: {sim_par_out}
        \t$(HAMMER_EXEC) {env_confs} -p {sim_par_out} $(HAMMER_EXTRA_ARGS) -o {power_sim_par_in} --obj_dir {obj_dir} sim-to-power

        {power_par_in}: {par_out}
        \t$(HAMMER_EXEC) {env_confs} -p {par_out} $(HAMMER_EXTRA_ARGS) -o {power_par_in} --obj_dir {obj_dir} par-to-power

        {power_par_out}: {power_sim_par_in} {power_par_in} $(HAMMER_POWER_PAR_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {power_sim_par_in} -p {power_par_in} $(HAMMER_EXTRA_ARGS) --power_rundir {power_par_run_dir} --obj_dir {obj_dir} power{suffix}

        {drc_in}: {par_out}
        \t$(HAMMER_EXEC) {env_confs} -p {par_out} $(HAMMER_EXTRA_ARGS) -o {drc_in} --obj_dir {obj_dir} par-to-drc

        {drc_out}: {drc_in} $(HAMMER_DRC_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {drc_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} drc{suffix}

        {lvs_in}: {par_out}
        \t$(HAMMER_EXEC) {env_confs} -p {par_out} $(HAMMER_EXTRA_ARGS) -o {lvs_in} --obj_dir {obj_dir} par-to-lvs

        {lvs_out}: {lvs_in} $(HAMMER_LVS_DEPENDENCIES)
        \t$(HAMMER_EXEC) {env_confs} -p {lvs_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} lvs{suffix}

        # Redo steps
        # These intentionally break the dependency graph, but allow the flexibility to rerun a step after changing a config.
        # Hammer doesn't know what settings impact synthesis only, e.g., so these are for power-users who "know better."
        # The HAMMER_EXTRA_ARGS variable allows patching in of new configurations with -p or using --to_step or --from_step, for example.
        .PHONY: redo-sim-rtl{suffix} redo-syn{suffix} redo-sim-syn{suffix} redo-par{suffix} redo-sim-par{suffix} redo-power-par{suffix} redo-drc{suffix} redo-lvs{suffix}

        redo-sim-rtl{suffix}:
        \t$(HAMMER_EXEC) {env_confs} {p_sim_rtl_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_rtl_run_dir} --obj_dir {obj_dir} sim{suffix}

        redo-syn{suffix}:
        \t$(HAMMER_EXEC) {env_confs} {p_syn_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} syn{suffix}

        redo-sim-syn{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {sim_syn_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_syn_run_dir} --obj_dir {obj_dir} sim{suffix}

        redo-par{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {par_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} par{suffix}

        redo-sim-par{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {sim_par_in} $(HAMMER_EXTRA_ARGS) --sim_rundir {sim_par_run_dir} --obj_dir {obj_dir} sim{suffix}

        redo-power-par{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {power_sim_par_in} -p {power_par_in} $(HAMMER_EXTRA_ARGS) --power_rundir {power_par_run_dir} --obj_dir {obj_dir} power{suffix}

        redo-drc{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {drc_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} drc{suffix}

        redo-lvs{suffix}:
        \t$(HAMMER_EXEC) {env_confs} -p {lvs_in} $(HAMMER_EXTRA_ARGS) --obj_dir {obj_dir} lvs{suffix}

        """)

    if not dependency_graph:
        # Flat flow
        top_module = str(driver.database.get_setting("synthesis.inputs.top_module"))

        # TODO make this DRY
        sim_rtl_run_dir = os.path.join(obj_dir, "sim-rtl-rundir")
        syn_run_dir = os.path.join(obj_dir, "syn-rundir")
        sim_syn_run_dir = os.path.join(obj_dir, "sim-syn-rundir")
        par_run_dir = os.path.join(obj_dir, "par-rundir")
        sim_par_run_dir = os.path.join(obj_dir, "sim-par-rundir")
        power_par_run_dir = os.path.join(obj_dir, "power-par-rundir")
        drc_run_dir = os.path.join(obj_dir, "drc-rundir")
        lvs_run_dir = os.path.join(obj_dir, "lvs-rundir")

        p_sim_rtl_in = proj_confs
        sim_rtl_out = os.path.join(sim_rtl_run_dir, "sim-output-full.json")
        p_syn_in = proj_confs
        syn_out = os.path.join(syn_run_dir, "syn-output-full.json")
        sim_syn_in = os.path.join(obj_dir, "sim-syn-input.json")
        sim_syn_out = os.path.join(sim_syn_run_dir, "sim-output-full.json")
        par_in = os.path.join(obj_dir, "par-input.json")
        par_out = os.path.join(par_run_dir, "par-output-full.json")
        sim_par_in = os.path.join(obj_dir, "sim-par-input.json")
        sim_par_out = os.path.join(sim_par_run_dir, "sim-output-full.json")
        power_sim_par_in = os.path.join(obj_dir, "power-sim-par-input.json")
        power_par_in = os.path.join(obj_dir, "power-par-input.json")
        power_par_out = os.path.join(power_par_run_dir, "power-output-full.json")
        drc_in = os.path.join(obj_dir, "drc-input.json")
        drc_out = os.path.join(drc_run_dir, "drc-output-full.json")
        lvs_in = os.path.join(obj_dir, "lvs-input.json")
        lvs_out = os.path.join(lvs_run_dir, "lvs-output-full.json")

        par_to_syn = ""

        output += make_text.format(suffix="", mod=top_module, env_confs=env_confs, obj_dir=obj_dir, syn_deps=syn_deps,
            par_to_syn=par_to_syn,
            p_sim_rtl_in=p_sim_rtl_in, sim_rtl_out=sim_rtl_out, sim_rtl_run_dir=sim_rtl_run_dir,
            sim_syn_in=sim_syn_in, sim_syn_out=sim_syn_out, sim_syn_run_dir=sim_syn_run_dir,
            sim_par_in=sim_par_in, sim_par_out=sim_par_out, sim_par_run_dir=sim_par_run_dir,
            p_syn_in=p_syn_in, syn_out=syn_out, par_in=par_in, par_out=par_out,
            power_sim_par_in=power_sim_par_in, power_par_in=power_par_in, power_par_out=power_par_out, power_par_run_dir=power_par_run_dir,
            drc_in=drc_in, drc_out=drc_out, lvs_in=lvs_in, lvs_out=lvs_out)
    else:
        # Hierarchical flow
        for node, edges in dependency_graph.items():
            out_edges = edges[1]

            # TODO make this DRY
            sim_rtl_run_dir = os.path.join(obj_dir, "sim-rtl-" + node)
            syn_run_dir = os.path.join(obj_dir, "syn-" + node)
            sim_syn_run_dir = os.path.join(obj_dir, "sim-syn-" + node)
            par_run_dir = os.path.join(obj_dir, "par-" + node)
            sim_par_run_dir = os.path.join(obj_dir, "sim-par-" + node)
            power_par_run_dir = os.path.join(obj_dir, "power-par-" + node)
            drc_run_dir = os.path.join(obj_dir, "drc-" + node)
            lvs_run_dir = os.path.join(obj_dir, "lvs-" + node)

            p_sim_rtl_in = proj_confs
            sim_rtl_out = os.path.join(sim_rtl_run_dir, "sim-output-full.json")
            p_syn_in = proj_confs
            syn_out = os.path.join(syn_run_dir, "syn-output-full.json")
            sim_syn_in = os.path.join(obj_dir, "sim-syn-{}-input.json".format(node))
            sim_syn_out = os.path.join(sim_syn_run_dir, "sim-output-full.json")
            par_in = os.path.join(obj_dir, "par-{}-input.json".format(node))
            par_out = os.path.join(par_run_dir, "par-output-full.json")
            sim_par_in = os.path.join(obj_dir, "sim-par-{}-input.json".format(node))
            sim_par_out = os.path.join(sim_par_run_dir, "sim-output-full.json")
            power_sim_par_in = os.path.join(obj_dir, "power-sim-par-{}-input.json".format(node))
            power_par_in = os.path.join(obj_dir, "power-par-{}-input.json".format(node))
            power_par_out = os.path.join(power_par_run_dir, "power-output-full.json")
            drc_in = os.path.join(obj_dir, "drc-{}-input.json".format(node))
            drc_out = os.path.join(drc_run_dir, "drc-output-full.json")
            lvs_in = os.path.join(obj_dir, "lvs-{}-input.json".format(node))
            lvs_out = os.path.join(lvs_run_dir, "lvs-output-full.json")

            # need to revert this each time
            syn_deps = "$(HAMMER_DEPENDENCIES)"
            par_to_syn = ""
            if len(out_edges) > 0:
                syn_deps = os.path.join(obj_dir, "syn-{}-input.json".format(node))
                p_syn_in = "-p {}".format(syn_deps) + " " + p_syn_in
                out_confs = [os.path.join(obj_dir, "par-" + x, "par-output-full.json") for x in out_edges]
                prereqs = " ".join(out_confs)
                pstring = " ".join(["-p " + x for x in out_confs])
                par_to_syn = textwrap.dedent("""
                    {syn_deps}: {prereqs}
                    \t$(HAMMER_EXEC) {env_confs} {pstring} -o {syn_deps} --obj_dir {obj_dir} hier-par-to-syn
                    """.format(syn_deps=syn_deps, prereqs=prereqs, env_confs=env_confs, pstring=pstring,
                    p_syn_in=p_syn_in, obj_dir=obj_dir))

            output += make_text.format(suffix="-"+node, mod=node, env_confs=env_confs, obj_dir=obj_dir, syn_deps=syn_deps,
                par_to_syn=par_to_syn,
                p_sim_rtl_in=p_sim_rtl_in, sim_rtl_out=sim_rtl_out, sim_rtl_run_dir=sim_rtl_run_dir,
                sim_syn_in=sim_syn_in, sim_syn_out=sim_syn_out, sim_syn_run_dir=sim_syn_run_dir,
                sim_par_in=sim_par_in, sim_par_out=sim_par_out, sim_par_run_dir=sim_par_run_dir,
                p_syn_in=p_syn_in, syn_out=syn_out, par_in=par_in, par_out=par_out,
                power_sim_par_in=power_sim_par_in, power_par_in=power_par_in, power_par_out=power_par_out, power_par_run_dir=power_par_run_dir,
                drc_in=drc_in, drc_out=drc_out, lvs_in=lvs_in, lvs_out=lvs_out)

    with open(makefile, "w") as f:
        f.write(output)

    return dependency_graph

BuildSystems = {
    "make": build_makefile,
    "none": build_noop
}  # type: Dict[str, Callable[[HammerDriver, Callable[[str], None]], dict]]
