# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from charmhelpers.core.strutils import (
    bytes_from_string
)

from charmhelpers.core.hookenv import (
    is_relation_made,
    relation_ids,
    relation_get,
    related_units,
    service_name,
    config,
    log as juju_log,
    ERROR
)

from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    ApacheSSLContext as SSLContext,
    BindHostContext
)

from charmhelpers.contrib.hahelpers.cluster import (
    determine_apache_port,
    determine_api_port,
)

from charmhelpers.contrib.openstack.utils import (
    os_release,
    CompareOpenStackReleases,
)


class GlanceContext(OSContextGenerator):

    def __call__(self):
        ctxt = {
            'disk_formats': config('disk-formats')
        }
        if config('container-formats'):
            ctxt['container_formats'] = config('container-formats')

        if config('filesystem-store-datadir'):
            ctxt['filesystem_store_datadir'] = (
                config('filesystem-store-datadir'))

        image_size_cap = config('image-size-cap')
        if image_size_cap:
            try:
                ctxt['image_size_cap'] = bytes_from_string(
                    image_size_cap.replace(' ', '').upper())
            except (ValueError, KeyError):
                juju_log('Unable to parse value for image-size-cap ({}), '
                         'see config.yaml for information about valid '
                         'formatting'.format(config('image-size-cap')),
                         level=ERROR)
                raise
        return ctxt


class GlancePolicyContext(OSContextGenerator):
    """This Context is only used from Ussuri onwards.  At Ussuri, Glance
    implemented policy-in-code, and thus didn't ship with a policy.json.
    Therefore, the charm introduces a 'policy.yaml' file that is used to
    provide the override here.

    Note that this is separate from policy overrides as it's a charm config
    option that has existed prior to its introduction.

    Update *_image_location policy to restrict to admin role.

    We do this unconditonally and keep a record of the original as installed by
    the package.
    """

    def __call__(self):
        if config('restrict-image-location-operations'):
            policy_value = 'role:admin'
        else:
            policy_value = ''

        ctxt = {
            "get_image_location": policy_value,
            "set_image_location": policy_value,
            "delete_image_location": policy_value,
        }
        return ctxt


class CephGlanceContext(OSContextGenerator):
    interfaces = ['ceph-glance']

    def __call__(self):
        """Used to generate template context to be added to glance-api.conf in
        the presence of a ceph relation.
        """
        if not is_relation_made(relation="ceph",
                                keys="key"):
            return {}
        service = service_name()
        if config('pool-type') == 'erasure-coded':
            pool_name = (
                config('ec-rbd-metadata-pool') or
                "{}-metadata".format(config('rbd-pool-name') or
                                     service)
            )
        else:
            if config('rbd-pool-name'):
                pool_name = config('rbd-pool-name')
            else:
                pool_name = service
        return {
            # pool created based on service name.
            'rbd_pool': pool_name,
            'rbd_user': service,
            'expose_image_locations': config('expose-image-locations')
        }


class ObjectStoreContext(OSContextGenerator):
    interfaces = ['object-store']

    def __call__(self):
        """Object store config.
        Used to generate template context to be added to glance-api.conf in
        the presence of a 'object-store' relation.
        """
        if not relation_ids('object-store'):
            return {}
        return {
            'swift_store': True,
        }


class CinderStoreContext(OSContextGenerator):
    interfaces = ['cinder-volume-service', 'storage-backend']

    def __call__(self):
        """Cinder store config.
        Used to generate template context to be added to glance-api.conf in
        the presence of a 'cinder-volume-service' relation or in the
        presence of a flag 'cinder-backend' in the 'storage-backend' relation.
        """
        if relation_ids('cinder-volume-service'):
            return {'cinder_store': True}
        for rid in relation_ids('storage-backend'):
            for unit in related_units(rid):
                value = relation_get('cinder-backend', rid=rid, unit=unit)
                # value is a boolean flag
                return {'cinder_store': value}
        return {}


class MultiBackendContext(OSContextGenerator):

    def _get_ceph_config(self):
        ceph_ctx = CephGlanceContext()()
        if not ceph_ctx:
            return
        ctx = {
            "rbd_store_chunk_size": 8,
            "rbd_store_pool": ceph_ctx["rbd_pool"],
            "rbd_store_user": ceph_ctx["rbd_user"],
            "rados_connect_timeout": 0,
            "rbd_store_ceph_conf": "/etc/ceph/ceph.conf",
        }
        return ctx

    def _get_swift_config(self):
        swift_ctx = ObjectStoreContext()()
        if not swift_ctx or swift_ctx.get("swift_store", False) is False:
            return
        ctx = {
            "default_swift_reference": "swift",
            "swift_store_config_file": "/etc/glance/glance-swift.conf",
            "swift_store_create_container_on_put": "true",
        }
        return ctx

    def __call__(self):
        ctxt = {
            "enabled_backend_configs": {},
            "enabled_backends": None,
            "default_store_backend": None,
        }
        backends = []

        local_fs = config('filesystem-store-datadir')
        if local_fs:
            backends.append("local:file")
            ctxt["enabled_backend_configs"]["local"] = {
                "filesystem_store_datadir": local_fs,
                "store_description": "Local filesystem store",
            }
        ceph_ctx = self._get_ceph_config()
        if ceph_ctx:
            backends.append("ceph:rbd")
            ctxt["enabled_backend_configs"]["ceph"] = ceph_ctx
            ctxt["default_store_backend"] = "ceph"

        swift_ctx = self._get_swift_config()
        if swift_ctx:
            backends.append("swift:swift")
            ctxt["enabled_backend_configs"]["swift"] = swift_ctx
            if not ctxt["default_store_backend"]:
                ctxt["default_store_backend"] = "swift"

        if local_fs and not ctxt["default_store_backend"]:
            ctxt["default_store_backend"] = "local"

        if len(backends) > 0:
            ctxt["enabled_backends"] = ", ".join(backends)
        return ctxt


class MultiStoreContext(OSContextGenerator):

    def __call__(self):
        stores = ['glance.store.filesystem.Store', 'glance.store.http.Store']
        store_mapping = {
            'ceph': 'glance.store.rbd.Store',
            'object-store': 'glance.store.swift.Store',
        }
        for store_relation, store_type in store_mapping.items():
            if relation_ids(store_relation):
                stores.append(store_type)
        _release = os_release('glance-common')
        if ((relation_ids('cinder-volume-service') or
                relation_ids('storage-backend')) and
                CompareOpenStackReleases(_release) >= 'mitaka'):
            # even if storage-backend is present with cinder-backend=False it
            # means that glance should not store images in cinder by default
            # but can read images from cinder.
            stores.append('glance.store.cinder.Store')
        stores.sort()
        return {
            'known_stores': ','.join(stores)
        }


class HAProxyContext(OSContextGenerator):
    interfaces = ['cluster']

    def __call__(self):
        '''Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend glance-api.conf context with correct bind_port
        '''
        haproxy_port = 9292
        apache_port = determine_apache_port(9292, singlenode_mode=True)
        api_port = determine_api_port(9292, singlenode_mode=True)

        ctxt = {
            'service_ports': {'glance_api': [haproxy_port, apache_port]},
            'bind_port': api_port,
        }
        return ctxt


class ApacheSSLContext(SSLContext):
    interfaces = ['https']
    external_ports = [9292]
    service_namespace = 'glance'

    def __call__(self):
        return super(ApacheSSLContext, self).__call__()


class LoggingConfigContext(OSContextGenerator):

    def __call__(self):
        return {'debug': config('debug'), 'verbose': config('verbose')}


class GlanceIPv6Context(BindHostContext):

    def __call__(self):
        ctxt = super(GlanceIPv6Context, self).__call__()
        if config('prefer-ipv6'):
            ctxt['registry_host'] = '[::]'
        else:
            ctxt['registry_host'] = '0.0.0.0'

        return ctxt
