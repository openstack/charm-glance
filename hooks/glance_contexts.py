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
    ERROR,
    WARNING
)

from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    ApacheSSLContext as SSLContext,
    BindHostContext,
    VolumeAPIContext,
    IdentityServiceContext,
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


class GlanceImageImportContext(OSContextGenerator):

    def __call__(self):
        ctxt = {}
        ctxt['image_import_plugins'] = []
        if config('image-conversion'):
            ctxt['image_import_plugins'].append('image_conversion')

        if config('custom-import-properties'):
            try:
                self.validate_custom_import_properties()
                ctxt['image_import_plugins'].append('inject_image_metadata')
                ctxt['custom_import_properties'] = (
                    config('custom-import-properties')
                )
            except (ValueError):
                juju_log('Unable to validate custom-import-properties ({}), '
                         'see config.yaml for information about valid '
                         'formatting'
                         .format(config('custom-import-properties')),
                         level=ERROR)
                raise
        return ctxt

    def validate_custom_import_properties(self):
        """Check the format of 'custom-import-properties' config parameter,
        it should be a string of comma delimited key:value pairs
        """
        props = config('custom-import-properties')
        if not isinstance(props, str):
            raise ValueError('not a string')
        # Empty string is valid
        if props == '':
            return
        # Check key value pairs
        props_list = props.split(',')
        for prop in props_list:
            if ":" not in prop:
                raise ValueError('value not found for property: {}'
                                 .format(prop))
        return


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


class ExternalS3Context(OSContextGenerator):
    required_config_keys = (
        "s3-store-host",
        "s3-store-access-key",
        "s3-store-secret-key",
        "s3-store-bucket",
    )

    def __call__(self):
        try:
            self.validate()
        except ValueError:
            # ValueError will be handled in assess_status and the charm status
            # will be blocked there. We will return the empty context here not
            # to block the template rendering itself.
            return {}

        if config("s3-store-host"):
            ctxt = {
                "s3_store_host": config("s3-store-host"),
                "s3_store_access_key": config("s3-store-access-key"),
                "s3_store_secret_key": config("s3-store-secret-key"),
                "s3_store_bucket": config("s3-store-bucket"),
            }
            if config("expose-image-locations"):
                juju_log("Forcibly overriding expose_image_locations "
                         "not to expose S3 credentials", level=WARNING)
                ctxt["expose_image_locations"] = False
            return ctxt

        return {}

    def validate(self):
        required_values = [
            config(key) for key in self.required_config_keys
        ]
        if all(required_values):
            # The S3 backend was once removed in Newton development cycle and
            # added back in Ussuri cycle in Glance upstream. As we rely on
            # python3-boto3 in the charm, don't enable the backend before
            # Ussuri release.
            _release = os_release("glance-common")
            if not CompareOpenStackReleases(_release) >= "ussuri":
                juju_log(
                    "Not enabling S3 backend: The charm supports S3 backed "
                    "only for Ussuri or later releases. Your release is "
                    "{}".format(_release),
                    level=ERROR,
                )
                raise ValueError("{} is not supported".format(_release))
        elif any(required_values):
            juju_log(
                "Unable to use S3 backend without all required S3 options "
                "defined. Missing keys: {}".format(
                    " ".join(
                        (k for k in self.required_config_keys if not config(k))
                    )
                ),
                level=ERROR,
            )
            raise ValueError("Missing necessary config options")


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

    def _get_s3_config(self):
        s3_ctx = ExternalS3Context()()
        if not s3_ctx:
            return
        ctx = {
            "s3_store_host": s3_ctx["s3_store_host"],
            "s3_store_access_key": s3_ctx["s3_store_access_key"],
            "s3_store_secret_key": s3_ctx["s3_store_secret_key"],
            "s3_store_bucket": s3_ctx["s3_store_bucket"],
        }
        return ctx

    def _get_cinder_config(self):
        cinder_ctx = CinderStoreContext()()
        if not cinder_ctx or cinder_ctx.get("cinder_store", False) is False:
            return

        return cinder_ctx

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

        s3_ctx = self._get_s3_config()
        if s3_ctx:
            backends.append("s3:s3")
            ctxt["enabled_backend_configs"]["s3"] = s3_ctx
            if not ctxt["default_store_backend"]:
                ctxt["default_store_backend"] = "s3"

        cinder_ctx = self._get_cinder_config()
        if cinder_ctx:
            cinder_volume_types = config('cinder-volume-types')
            volume_types_str = cinder_volume_types or 'cinder'
            volume_types = volume_types_str.split(',')
            default_backend = volume_types[0]
            for volume_type in volume_types:
                backends.append(volume_type+':cinder')

            # Add backend cinder_volume_type if cinder-volume-types configured
            # In case cinder-volume-types not configured in charm, glance-api
            # backend cinder_volume_type should be left blank so that glance
            # creates volume in cinder without specifying any volume type.
            if cinder_volume_types:
                keystone_ctx = IdentityServiceContext()()
                for volume_type in volume_types:
                    ctxt['enabled_backend_configs'][volume_type] = {
                        'cinder_volume_type': volume_type,
                        'cinder_http_retries': config('cinder-http-retries'),
                        'cinder_state_transition_timeout': config(
                            'cinder-state-transition-timeout'),
                    }
                    if keystone_ctx:
                        ctxt['enabled_backend_configs'][volume_type].update({
                            'cinder_store_user_name': keystone_ctx.get(
                                'admin_user'),
                            'cinder_store_password': keystone_ctx.get(
                                'admin_password'),
                            'cinder_store_project_name': keystone_ctx.get(
                                'admin_tenant_name'),
                            'cinder_store_auth_address': keystone_ctx.get(
                                'keystone_authtoken').get('auth_url'),
                        })
            else:
                # default cinder volume type cinder
                ctxt['enabled_backend_configs']['cinder'] = {
                    'cinder_http_retries': config('cinder-http-retries'),
                    'cinder_state_transition_timeout': config(
                        'cinder-state-transition-timeout'),
                }

            # Add internal endpoints if use-internal-endpoints set to true
            if config('use-internal-endpoints'):
                vol_api_ctxt = VolumeAPIContext('glance-common')()
                volume_catalog_info = vol_api_ctxt['volume_catalog_info']
                for volume_type in volume_types:
                    if volume_type not in ctxt['enabled_backend_configs']:
                        ctxt['enabled_backend_configs'][volume_type] = {}
                    ctxt['enabled_backend_configs'][volume_type].update(
                        {'cinder_catalog_info': volume_catalog_info})

            if not ctxt["default_store_backend"]:
                ctxt["default_store_backend"] = default_backend

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
