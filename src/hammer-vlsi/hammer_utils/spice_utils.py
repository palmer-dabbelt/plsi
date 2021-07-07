#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  spice_utils.py
#  Misc SPICE utilities
#
#  See LICENSE for licence details.

import re
from typing import Tuple, Optional, List, Set, Dict
from enum import Enum

class SpiceUtils:

    # Multilines in spice start with a + character
    MultilinePattern = re.compile("(?:\s*\n\+)+\s*", flags=re.DOTALL)
    ModuleDefPattern = re.compile("^(\.subckt\s+)(?P<dname>[^\s]+)(\s+.*)$", flags=re.IGNORECASE|re.MULTILINE)
    ModuleInstPattern = re.compile("^(x.*?\s)(?P<mname>[^\s]+)(\s*)$", flags=re.IGNORECASE|re.MULTILINE)
    EndModulePattern = re.compile("^\.ends.*$", flags=re.IGNORECASE|re.MULTILINE)
    Tokens = [
        ('SUBCKT', ModuleDefPattern.pattern),
        ('ENDS', EndModulePattern.pattern),
        ('INST', ModuleInstPattern.pattern)
    ]
    TokenRegex = re.compile('|'.join('(?P<%s>%s)' % t for t in Tokens), flags=re.IGNORECASE|re.MULTILINE)

    @staticmethod
    def uniquify_spice(sources: List[str]) -> List[str]:
        """
        Uniquify the provided SPICE sources. If a module name exists in multiple files, each duplicate module will be
        renamed. If the original name of a duplicated module is used in a file where it is not defined, an
        exception is thrown as it is impossible to know which renamed module to use. For example:

        - file1.sp defines B and A, which instantiates B
        - file2.sp defines B and C, which instantiates B

        B would be renamed to B_0 in file1.sp
        B would be renamed to B_1 in file2.sp

        However, if file3.sp defines D, which instantiates B, an exception would be raised because we don't know if we
        should chose B_0 or B_1.

        :param sources: A list of the contents of SPICE source files (not the filenames)
        :return: A list of SPICE sources with unique modules
        """
        sources_no_multiline = [SpiceUtils.remove_multilines(s) for s in sources]
        module_trees = [SpiceUtils.parse_module_tree(s) for s in sources_no_multiline]
        found_modules = set()  # type: Set[str]
        duplicates = set()  # type: Set[str]
        extmods = set()  # type: Set[str]
        for tree in module_trees:
            extmods.update(set(item for sublist in tree.values() for item in sublist if item not in set(tree.keys())))
            for module in tree:
                if module in found_modules:
                    duplicates.add(module)
                found_modules.add(module)

        invalid_extmods = extmods.intersection(duplicates)
        if len(invalid_extmods) != 0:
            raise ValueError("Unable to resolve master for duplicate SPICE module name: {}".format(",".join(invalid_extmods)))

        def replace_source(source: str) -> str:
            replacements = {}  # type: Dict[str, str]
            for old in duplicates:
                i = 0
                new = old
                while new in found_modules:
                    new = "{d}_{i}".format(d=old, i=i)
                    i = i + 1
                found_modules.add(new)
                replacements[old] = new

            return SpiceUtils.replace_modules(source, replacements)

        return [replace_source(s) for s in sources_no_multiline]


    @staticmethod
    def parse_module_tree(s: str) -> Dict[str, Set[str]]:
        """
        Parse a SPICE file and return a dictionary that contains all found modules pointing to lists of their submodules.
        The SPICE file must not contain multiline statements.

        :param s: A SPICE file without any multiline statements
        :return: A dictionary whose keys are all found modules and whose values are the list of submodules
        """
        in_module = False
        module_name = ""
        tree = {}  # type: Dict[str, Set[str]]
        for m in SpiceUtils.TokenRegex.finditer(s):
            kind = m.lastgroup
            if kind == 'SUBCKT':
                module_name = m.group("dname")
                in_module = True
                if module_name in tree:
                    raise ValueError("Multiple SPICE subckt definitions for \"{}\" in the same file".format(module_name))
                tree[module_name] = set()
            elif kind == 'ENDS':
                in_module = False
            elif kind == 'INST':
                if not in_module:
                    raise ValueError("Malformed SPICE source while parsing: \"{}\"".format(m.group()))
                tree[module_name].add(m.group("mname"))
            else:
                assert False, "Should not get here"

        return tree

    @staticmethod
    def replace_modules(source: str, mapping: Dict[str, str]) -> str:
        """
        Replace module names in a provided SPICE file by the provided mapping.
        The SPICE file must not contain multiline statements.


        :param source: The input SPICE source without any multiline statements
        :param mapping: A dictionary of old module names mapped to new module names
        :return: SPICE source with the module names replaced
        """
        # Not giving m a type because its type is different in different python3 versions :(
        def repl_fn(m) -> str:
            if m.group(2) in mapping:
                return m.group(1) + mapping[m.group(2)] + m.group(3)
            else:
                return m.group(0)

        return SpiceUtils.ModuleInstPattern.sub(repl_fn, SpiceUtils.ModuleDefPattern.sub(repl_fn, source))

    @staticmethod
    def remove_multilines(s: str) -> str:
        """
        Remove all multiline statements from the given SPICE source.

        :param s: The SPICE source
        :return: SPICE source without multiline statements
        """
        return SpiceUtils.MultilinePattern.sub(" ", s)



