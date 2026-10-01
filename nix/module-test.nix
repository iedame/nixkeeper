# The NixOS module in a VM (checks.module on Linux; needs KVM, which CI has):
# the timers, the frequent checks against data like a sync leaves, and the
# page with its data on nginx. The VM has no internet, so no real sync.
{ pkgs, self }:
pkgs.testers.runNixOSTest {
  name = "nixkeeper";

  nodes.machine = {
    imports = [ self.nixosModules.default ];
    services.nixkeeper = {
      enable = true;
      lists.maintainers = [ "iedame" ];
      nginx.virtualHost = "localhost";
    };
  };

  testScript = ''
    import json

    machine.wait_for_unit("multi-user.target")
    machine.succeed("systemctl list-timers | grep nixkeeper-sync.timer")
    machine.succeed("systemctl list-timers | grep nixkeeper-checks.timer")

    with subtest("the checks wait for a first sync"):
        machine.succeed("systemctl start nixkeeper-checks.service")
        machine.succeed(
            "journalctl -u nixkeeper-checks.service | grep -q 'unmet condition'"
        )

    with subtest("the lists are the module's, as JSON"):
        lists = machine.succeed(
            "systemctl show nixkeeper-sync.service -p Environment"
            " | grep -o 'NIXKEEPER_LISTS=[^ ]*' | cut -d= -f2"
        ).strip()
        assert json.loads(machine.succeed(f"cat {lists}"))["maintainers"] == ["iedame"]

    # Data as a sync leaves it: one package, up to date, nothing to look up.
    index = {
        "checkedAt": "2026-10-01T06:00:00+00:00",
        "packages": [{"name": "unciv", "attrs": ["unciv"], "nixStatus": "newest"}],
    }
    machine.succeed(
        "install -d -o nixkeeper -g nixkeeper /var/lib/nixkeeper/data"
        f" && echo '{json.dumps(index)}' > /var/lib/nixkeeper/data/index.json"
        " && chown nixkeeper:nixkeeper /var/lib/nixkeeper/data/index.json"
    )

    with subtest("the frequent checks run against it"):
        machine.succeed("systemctl start nixkeeper-checks.service")
        # Not "log": the test driver's own logger is called that.
        journal = machine.succeed("journalctl -u nixkeeper-checks.service")
        assert "No frequent update checks" in journal, journal
        assert "Nothing outdated" in journal, journal

    with subtest("nginx serves the page and the data next to it"):
        machine.wait_for_unit("nginx.service")
        machine.wait_for_open_port(80)
        assert "<title>nixkeeper" in machine.succeed("curl -sf http://localhost/")
        data = json.loads(machine.succeed("curl -sf http://localhost/data/index.json"))
        assert data["packages"][0]["name"] == "unciv"
        machine.fail("curl -sf --path-as-is http://localhost/data/../../etc/passwd")
  '';
}
