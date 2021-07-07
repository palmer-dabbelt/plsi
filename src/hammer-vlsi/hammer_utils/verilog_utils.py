#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  verilog_utils.py
#  Misc Verilog utilities (*shudders*)
#
#  See LICENSE for licence details.

import re

class VerilogUtils:
    @staticmethod
    def remove_comments(v: str) -> str:
        """
        Remove comments from the given Verilog source.

        :param v: Verilog source code
        :return: Source code without comments
        """
        # // style line comments
        line_comment_pattern = r"(//.*$)"
        without_line_comments = re.sub(line_comment_pattern, "", v, flags=re.MULTILINE)

        # /* */ style block comments
        block_comment_pattern = r"(/\*.*?\*/)"
        return re.sub(block_comment_pattern, "", without_line_comments, flags=re.DOTALL)

    @staticmethod
    def contains_module(v: str, module: str) -> bool:
        """
        Check if the given Verilog source contains the given module.

        :param v: Verilog source code
        :param module: Module to look for
        :return: True if the given module exists.
        """
        # Remove comments first to avoid false matches in the comments
        new_v = VerilogUtils.remove_comments(v)

        regex = "module\s+" + re.escape(module)
        return re.search(regex, new_v) is not None

    @staticmethod
    def remove_module(v: str, module: str) -> str:
        """
        Remove the given module from the given Verilog source, if it exists.

        :param v: Verilog source code
        :param module: Module to remove
        :return: Verilog with given module definition removed, if it exists
        """
        if not VerilogUtils.contains_module(v, module):
            # Don't risk touching the source if we don't think the module exists.
            return v

        regex = "(module\s+" + re.escape(module) + ".+?endmodule)"
        return re.sub(regex, "", v, flags=re.DOTALL)
