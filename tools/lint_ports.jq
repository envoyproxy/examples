def host:
    if type == "object" then (.published // "" | tostring)
    else
        tostring
        | sub("/[a-z]+$"; "")
        | if test(":[0-9]+$") then
            sub(":[0-9]+$"; "")
            | sub("^(\\[[^]]+\\]|[^:]+):(?=\\$\\{|[0-9])"; "")
          else "missing host: \(.)" end
    end;

[to_entries[] | .key as $file
 | .value.services // {} | to_entries[] | .key as $service
 | (.value.ports // [])[]
 | host
 | select(test("^\\$\\{PORT_[A-Z0-9_]+:-[0-9]+\\}$") | not)
 | "\($file): \($service): \(.)"]
| if length == 0 then empty else error(join("\n")) end
