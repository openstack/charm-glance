#!/bin/bash

CHARM="glance"

SERVICES="glance-api glance-registry"
PACKAGES="glance python-mysqldb python-swift python-keystone uuid haproxy"

GLANCE_REGISTRY_CONF="/etc/glance/glance-registry.conf"
GLANCE_REGISTRY_PASTE_INI="/etc/glance/glance-registry-paste.ini"
GLANCE_API_CONF="/etc/glance/glance-api.conf"
GLANCE_API_PASTE_INI="/etc/glance/glance-api-paste.ini"
CONF_DIR="/etc/glance"
HOOKS_DIR="$CHARM_DIR/hooks"

# Flag used to track config changes.
CONFIG_CHANGED="False"
if [[ -e "$HOOKS_DIR/lib/openstack-common" ]] ; then
  . $HOOKS_DIR/lib/openstack-common
else
  juju-log "ERROR: Couldn't load $HOOKS_DIR/lib/openstack-common." && exit 1
fi

function set_or_update {
  local key="$1"
  local value="$2"
  local file="$3"
  local section="$4"
  local conf=""
  [[ -z $key ]] && juju-log "ERROR: set_or_update(): value $value missing key" \
        && exit 1
  [[ -z $value ]] && juju-log "ERROR: set_or_update(): key $key missing value" \
        && exit 1

  case "$file" in
    "api") conf=$GLANCE_API_CONF ;;
    "api-paste") conf=$GLANCE_API_PASTE_INI ;;
    "registry") conf=$GLANCE_REGISTRY_CONF ;;
    "registry-paste") conf=$GLANCE_REGISTRY_PASTE_INI ;;
    *) juju-log "ERROR: set_or_update(): Invalid or no config file specified." \
        && exit 1 ;;
  esac

  [[ ! -e $conf ]] && juju-log "ERROR: set_or_update(): File not found $conf" \
        && exit 1

  if [[ "$(local_config_get "$conf" "$key" "$section")" == "$value" ]] ; then
    juju-log "$CHARM: set_or_update(): $key=$value already set in $conf."
    return 0
  fi

  cfg_set_or_update "$key" "$value" "$conf" "$section"
  CONFIG_CHANGED="True"
}

do_openstack_upgrade() {
  # update openstack components to those provided by a new installation source
  # it is assumed the calling hook has confirmed that the upgrade is sane.
  local rel="$1"
  shift
  local packages=$@
  orig_os_rel=$(get_os_codename_package "glance-common")
  new_rel=$(get_os_codename_install_source "$rel")

  # Backup the config directory.
  local stamp=$(date +"%Y%m%d%M%S")
  tar -pcf /var/lib/juju/$CHARM-backup-$stamp.tar $CONF_DIR

  # Setup apt repository access and kick off the actual package upgrade.
  configure_install_source "$rel"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get --option Dpkg::Options::=--force-confnew -y \
     install --no-install-recommends $packages

  # Update the new config files for existing relations.
  local r_id=""

  r_id=$(relation-ids shared-db)
  if [[ -n "$r_id" ]] ; then
    juju-log "$CHARM: Configuring database after upgrade to $rel."
    db_changed $r_id
  fi

  r_id=$(relation-ids identity-service)
  if [[ -n "$r_id" ]] ; then
    juju-log "$CHARM: Configuring identity service after upgrade to $rel."
    keystone_changed $r_id
  fi

  local ceph_ids="$(relation-ids ceph)"
  [[ -n "$ceph_ids" ]] && apt-get -y install ceph-common python-ceph
  for r_id in $ceph_ids ; do
    for unit in $(relation-list -r $r_id) ; do
      ceph_changed "$r_id" "$unit"
    done
  done

  [[ -n "$(relation-ids object-store)" ]] && object-store_joined
}

configure_https() {
  # request openstack-common setup reverse proxy mapping for API and registry
  # servers
  service_ctl glance-api stop
  if [[ -n "$(peer_units)" ]] || is_clustered ; then
    # haproxy may already be configured. need to push it back in the request
    # pipeline in preparation for a change from:
    #  from:  haproxy (9292) -> glance_api (9282)
    #  to:    ssl (9292) -> haproxy (9291) -> glance_api (9272)
    local next_server=$(determine_haproxy_port 9292)
    local api_port=$(determine_api_port 9292)
    configure_haproxy "glance_api:$next_server:$api_port"
  else
    # if not clustered, the glance-api is next in the pipeline.
    local api_port=$(determine_api_port 9292)
    local next_server=$api_port
  fi

  # setup https to point to either haproxy or directly to api server, depending.
  setup_https 9292:$next_server

  # configure servers to listen on new ports accordingly.
  set_or_update bind_port "$api_port" "api"
  service_ctl all start

  local r_id=""
  # (re)configure ks endpoint accordingly in ks and nova.
  for r_id in $(relation-ids identity-service) ; do
    keystone_joined "$r_id"
  done
  for r_id in $(relation-ids image-service) ; do
    image-service_joined "$r_id"
  done
}
