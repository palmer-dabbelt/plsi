Configuration system
===

The hammer/hammer-vlsi configuration system is centered around a key-value store. Keys are stored hierarchically, separated by periods. Legal keys are alphanumeric characters and underscores; periods are forbidden.

Hammer will "unpack" hierarchies for ease of configuration.

Configuration can be stored either in JSON or YAML format. Configurations in YAML format will be converted to JSON and applied before the JSON format, if that also exists.

The config builder (build-config.py) will use values in subsequent files to override values in earlier files. For example, if the config is built with "a.json b.json" and a.json defines `foo: "one"` and b.json defines `foo: "two"`, then
 the resulting setting will be `foo: "two"`.

Configuration precedence
========================

There is a chain of precedence for the configuration system:

- builtins: Built-in variables defined by hammer-vlsi.
- core: Core settings defined by hammer-vlsi and available for overriding.
- tools: Settings provided by various tools.
- technology: Settings provided by various technologies.
- environment: User-supplied environment settinggs (e.g. CAD tool paths, licence servers, etc)
- project: Settings specific to a run of hammer-vlsi.

The hammer-vlsi frontend/command line interface allows the latter two (environment and project) to be overridden. All previous settings are defined by hammer-vlsi libraries or the hammer-vlsi core.

The hammer-vlsi frontend will also dump an output copy of the project JSON along with the outputs in order to allow for modular re-use of hammer-vlsi.

Meta directives
===============
Sometimes we want to append to pre-existing setting or substitute pre-existing setting.

When reading a setting, if the setting has an accompanying `_meta` setting, it will be used when getting the setting. The `_meta` setting is be a string currently specifying one keyword.  Currently valid `_meta` attributes are:

`append` - appends to the given array. The given base setting must be an array.
Example:
If parent JSON has `"test": ["foo"]` and child JSON has
```
{
  "test": ["bar"],
  "test_meta": append
}
```
then output JSON will be:
```
{
  "test": ["foo", "bar"]
}
```

`subst`, which means that if the keyword `subst` is present, `get-config` will substitute variables using curly braces. Example: if `foo: "one"`, `bar: "{foo} two"`, and `bar_meta: "subst"`, then `get-config` for `bar` will return "one two".

base: {}
update: {"a": "{b}", "a_meta": "subst", 
         "b": "{a}", "b_meta": "subst" }
--> results in blank/error since a will try to look for b in base, and b will look for a in base.

`dynamicsubst` means that the given config will not be substituted until all known configs have been bound. Use this to enable settings to be overwritten until the very end.

base: {}
update: {"a": "{b}", "a_meta": "dynamicsubst", 
         "b": "{a}", "b_meta": "dynamicsubst"}

All dynamic meta directivs are single-stage.

meta config, but keyword is "script". If this keyword is present, it will execute the given script and substitute variables like so `{var_name}`
^ not implemented yet!!!

---
_meta config should be an array
meta files are specific to the config
_meta configs cannot have another _meta
substfile meta keyword. Reads file, substitutes variables, writes to object dir, replaces original var with new path.

Examples:

Given the following JSON configuration file:
```
{
  "top1": "top1_str",
  "top2.foo": {
    "a": "alpha",
    "b": "beta",
    "z": "zeta"
  }
}
```

This yields the following configuration:

 - `top1 = "top1_str"`
 - `top2.foo.a = "alpha"`
 - `top2.foo.b = "beta"`
 - `top2.foo.z = "zeta"`

Caveats
=======

- Settings with names like "yes" and "no" do not work since JSON automatically converts them to True/False booleans as keys.
