from nbtools.lintcmd.tenant_names import TenantNamesCommand

from ..nbstub import FakeNetbox


PATTERN = '^[a-z0-9][a-z0-9-]*[a-z0-9]$'


def a_netbox():
    nb = FakeNetbox()
    nb.add_tenant('acme-bv', description='ACME B.V.')
    nb.add_tenant('ACME B.V.', description='ACME B.V.')
    nb.add_tenant('resellers', group=True)
    nb.add_tenant('Resellers & Partners', group=True)

    return nb


def test_a_slug_style_name_is_fine():
    findings = TenantNamesCommand(a_netbox()).find()

    assert 'acme-bv' not in [finding.porcelain() for finding in findings]


def test_a_punctuated_tenant_name_is_reported():
    findings = TenantNamesCommand(a_netbox()).find()

    assert str(findings[0]) == (
        f"tenant 'ACME B.V.' #1201 name is not slug-style ({PATTERN})")


def test_tenant_groups_are_checked_too():
    findings = TenantNamesCommand(a_netbox()).find()

    assert str(findings[1]) == (
        "tenant-group 'Resellers & Partners' #1301 name is not "
        f'slug-style ({PATTERN}), and the description is empty')


def test_an_empty_description_is_only_mentioned_beside_a_bad_name():
    "A name needing no punctuating has nothing to put in the description"
    nb = FakeNetbox()
    nb.add_tenant('acme-bv')

    assert TenantNamesCommand(nb).find() == []


def test_a_name_may_start_with_a_digit():
    "Names like 7eleven are in use"
    nb = FakeNetbox()
    nb.add_tenant('7eleven', description='7-Eleven')
    nb.add_tenant('123', group=True)

    assert TenantNamesCommand(nb).find() == []


def test_a_single_character_name_is_too_short():
    nb = FakeNetbox()
    nb.add_tenant('x', description='Company X')

    assert [finding.porcelain() for finding in
            TenantNamesCommand(nb).find()] == ['x']


def test_two_characters_is_enough():
    nb = FakeNetbox()
    nb.add_tenant('xy')

    assert TenantNamesCommand(nb).find() == []


def test_a_name_may_hold_dashes_in_the_middle():
    nb = FakeNetbox()
    nb.add_tenant('acme-bv-2')

    assert TenantNamesCommand(nb).find() == []


def test_a_name_may_not_end_on_a_dash():
    "'acme-' reads as a fragment of something else"
    nb = FakeNetbox()
    nb.add_tenant('acme-', description='ACME')
    nb.add_tenant('-acme', description='ACME', group=True)

    assert [finding.porcelain() for finding in
            TenantNamesCommand(nb).find()] == ['acme-', '-acme']


def test_an_underscore_is_no_longer_allowed():
    "NetBox slugs allow one and the old rule did too; this reports it"
    nb = FakeNetbox()
    nb.add_tenant('acme_bv', description='ACME B.V.')

    assert [finding.porcelain() for finding in
            TenantNamesCommand(nb).find()] == ['acme_bv']


def test_an_upper_case_name_is_reported():
    nb = FakeNetbox()
    nb.add_tenant('AcmeBV', description='ACME B.V.')

    assert [finding.porcelain() for finding in
            TenantNamesCommand(nb).find()] == ['AcmeBV']


def test_command_reports_and_counts(capsys):
    assert TenantNamesCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out.startswith(
        '------------\n'
        'tenant-names\n'
        '------------\n'
        "- tenant 'ACME B.V.' #1201 ")


def test_command_porcelain_prints_bare_names(capsys):
    cmd = TenantNamesCommand(a_netbox())
    cmd.set_porcelain()

    assert cmd.run() == 2
    assert capsys.readouterr().out == (
        'ACME B.V.\n'
        'Resellers & Partners\n')


def test_a_clean_netbox_is_silent(capsys):
    assert TenantNamesCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
