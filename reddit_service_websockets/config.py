class ConfigurationError(Exception):
    def __init__(self, key, error):
        self.key = key
        self.error = error

    def __str__(self):
        return "%s: %s" % (self.key, self.error)


def parse_config(config, spec, root=None):
    parsed = {}
    for key, parser_or_spec in spec.iteritems():
        if root:
            key_path = "%s.%s" % (root, key)
        else:
            key_path = key

        if callable(parser_or_spec):
            parser = parser_or_spec

            try:
                raw_value = config[key_path]
            except KeyError:
                raise ConfigurationError(key, "not found")

            try:
                parsed[key] = parser(raw_value)
            except Exception as e:
                raise ConfigurationError(key, e)
        elif isinstance(parser_or_spec, dict):
            subspec = parser_or_spec
            parsed[key] = parse_config(config, subspec, root=key_path)
        else:
            raise ConfigurationError(key, "invalid spec")
    return parsed


def base64(text):
    import base64
    return base64.b64decode(text)


def comma_delimited(text):
    return filter(None, [x.strip() for x in text.split(",")])
