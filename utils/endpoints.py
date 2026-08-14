"""Preserves the flat endpoint namespace that predates the routes/ split.

Before the blueprint split every view was registered directly on the app, so its
endpoint was just the function name. The 19 templates address them that way --
``url_for('logout')``, ``url_for('user_management')`` -- as do the endpoint-name
strings handed out by inject_role_context(). Blueprints rename all of them to
``auth.logout``, ``admin.user_management`` and so on.

Rather than rewrite every template (this session must not touch them, and the
names would be equally correct either way), a build-error handler maps a bare
name back to its qualified endpoint. The result is exactly the namespace the app
had before: the same bare names resolve to the same URLs.

Two properties worth keeping:

* An unknown name still raises the original BuildError, so a typo -- or an
  endpoint a role is not meant to reach -- fails as loudly as it did before.
* Registration aborts if two blueprints expose the same view name, because then
  a bare name would be ambiguous and this shim would have to guess. Today all 31
  view functions are uniquely named, so the mapping is total and unambiguous.
"""
from flask import url_for


def register_flat_endpoint_aliases(app):
    """Map each unqualified view name onto its blueprint-qualified endpoint.

    Must be called after every blueprint is registered.
    """
    aliases = {}
    collisions = {}

    for endpoint in app.view_functions:
        if "." not in endpoint:
            continue
        bare_name = endpoint.rsplit(".", 1)[1]
        if bare_name in aliases:
            collisions.setdefault(bare_name, {aliases[bare_name]}).add(endpoint)
        aliases[bare_name] = endpoint

    if collisions:
        raise RuntimeError(
            "Two blueprints expose the same view name, so the flat endpoint namespace "
            f"the templates rely on is ambiguous: {collisions}. Rename one of them."
        )

    def resolve_flat_endpoint(error, endpoint, values):
        qualified = aliases.get(endpoint)
        if qualified is None:
            raise error
        return url_for(qualified, **values)

    app.url_build_error_handlers.append(resolve_flat_endpoint)
    return aliases
