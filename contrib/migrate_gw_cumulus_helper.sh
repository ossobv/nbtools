#!/bin/bash
#
# Helper for a very custom situation where:
# - Cumulus L3 switches are connected to VM hypervisors.
# - Each VM has one or more /31 IPs.
# - The switch has the gateway side of the /31s on VRF subinterfaces.
# - We want to move a VM from one hypervisor to another one:
#   this "migrates the gateway". (The moving of the VM itself is a
#   separate task which can be performed using proxmove(1).)
# - Moving the gateway in NetBox can be done nbsync `migrate-gateway` command.
# - But doing the "net add" and "net del" commands on the leaf might be
#   quicker.
# - This helper spells out what to run.
#
# Example:
#
# $ migrate_gw_cumulus_helper.sh UNRELATED_VM_ON_TARGET VM_TO_MOVE...
# > # Targets: leaf1:swp30 leaf2:swp30
# > leaf1: net add interface swp30.2100 ip address 1.2.3.4/31 # vrf VRF
# > leaf1: net del interface swp34.2100 ip address 1.2.3.4/31
# > leaf2: net add interface swp30.2100 ip address 1.2.3.4/31 # vrf VRF
# > leaf2: net del interface swp34.2100 ip address 1.2.3.4/31
# > #$ nbsync migrate-gateway -t leaf1:swp30 -t leaf2:swp30 VM_TO_MOVE
#
set -eu

get_gateways() {
    local vmname="$1"
    local ip gw
    for ip in $(nbdig -vi '' $1 |
            awk -vH="$vmname" '$1==H{gsub("[][]","",$2);print $2}'); do
        gw=$(echo "$ip" | sed -e 's/1$/0/;s/3$/2/;s/5$/4/;s/7$/6/;s/9$/8/')
        if test "$ip" = "$gw"; then
            gw=$(echo "$ip" | sed -e 's/0$/1/;s/2$/3/;s/4$/5/;s/6$/7/;s/8$/9/')
            if test "$ip" = "$gw"; then
                echo "$0: IP==GW fail on $ip for $vmname" >&2
               exit 1
            fi
        fi
        echo $gw
    done
}


# Take different host as target:
tgtvmname=${1:?need target VM to get GW info from}
shift

targets=()
while read dev gw2 iface vrf rest; do
    targets+=("$dev:${iface%.*}")  # iface without subinterface
done < <(for gw in $(get_gateways "$tgtvmname"); do
         nbdig -x "$gw" -vi ''; done)

echo "# Targets: ${targets[*]}"
echo

for vmname in "$@"; do
    for gw in $(get_gateways "$vmname"); do
        while read dev gw2 iface vrf rest; do
            echo "$dev: net del interface $iface ip address $gw/31"
            vrf_name=${vrf#*-}
            vrf_vlan=${vrf%-*}
            iface_suffix=${iface#*.}
        done < <(nbdig -x "$gw" -vi '')
        if test "${vrf_vlan#0}" != "${iface_suffix}"; then
            echo "$0: unexpected vrf/iface $vrf_vlan\
 $iface_suffix ($vmname)" >&2
            exit 1
        fi
        for tgt in ${targets[@]}; do
            echo "${tgt%:*}: net add interface ${tgt#*:}.${iface_suffix}\
 ip address $gw/31 # vrf $vrf_name"
        done
    done | sort -k3,3 -k1V
    echo -n '#$ nbsync migrate-gateway'
    for tgt in ${targets[@]}; do echo -n " -t $tgt"; done
    echo " $vmname"
    echo
done
