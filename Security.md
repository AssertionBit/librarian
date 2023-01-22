
# List of known issues

Here is the list of known secure issues that related to that project, but can
not be solved now, or in progress.

## Project related

List of issues, that appeared in project itself.

### Pickle arbitrary code execution

* Level: 10
* Side-dependency: False, Built-in
* Resolved: False

### Description

Using native pickle module for loading python objects could be compromised when
using side plugins. There is no internet connection, so only place, when 
problems could appear is loading plugins.

### Example usage

```python
# Example of exploit plugin that could be used
import pickle

import librarian


def compromised_code(files: List[str]):
    # Collects data and runs something
    ...


librarian.add_plugin(LanguageSpecs(
    "exploit",
    [],
    [],
    [],
    True,
    [],
    []
).with_loaded(compromised_code))
```

### Solution

Possibly run some sanity checks and exclude ability to check the system status,
local configs and etc. Pickle module could be restarted after installing each
plugin, so this could be as part of solution too.

## Redirected plugin installer

* Level: 10
* Side-dependency: True, requests
* Resolved: False

### Description

Network connection could be compromised and have force redirects to malware
localhost servers. Here is the example:

```sh
librarian install cpp
```

Which should make requests to one of these sites:

1. PyPi
2. Github

But if something goes wrong, librarian don't check the result and just install
the plugin as it is.

### Solution

Requests should make sanity checks of the requests. If redirect is performed,
then just mark that networking is compromised and stop requesting to network.

## Dependencies related

List of issues, that appeared in dependencies including system library.
