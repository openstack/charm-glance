# Overview

This charm provides the Glance image service for OpenStack.  It is intended to
be used alongside the other OpenStack components.

# Usage

Glance may be deployed in a number of ways.  This charm focuses on 3 main
configurations.  All require the existence of the other core OpenStack
services deployed via Juju charms, specifically: mysql, keystone and
nova-cloud-controller.  The following assumes these services have already
been deployed.

## Local Storage

In this configuration, Glance uses the local storage available on the server
to store image data:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller

## Swift backed storage

Glance can also use Swift Object storage for image storage.  Swift is often
deployed as part of an OpenStack cloud and provides increased resilience and
scale when compared to using local disk storage.  This configuration assumes
that you have already deployed Swift using the swift-proxy and swift-storage
charms:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance swift-proxy

This configuration can be used to support Glance in HA/Scale-out deployments.

## Ceph backed storage

In this configuration, Glance uses Ceph based object storage to provide
scalable, resilient storage of images.  This configuration assumes that you
have already deployed Ceph using the ceph charm:

    juju deploy glance
    juju add-relation glance keystone
    juju add-relation glance mysql
    juju add-relation glance nova-cloud-controller
    juju add-relation glance ceph

This configuration can also be used to support Glance in HA/Scale-out
deployments.

NOTE: Glance acts as a Ceph client in this case which requires IP (L3)
connectivity to ceph monitors and OSDs. For MAAS-based deployments this
can be addressed with network spaces (see the relevant section below).

## High availability

When more than one unit is deployed with the [hacluster][hacluster-charm]
application the charm will bring up an HA active/active cluster.

There are two mutually exclusive high availability options: using virtual IP(s)
or DNS. In both cases the hacluster subordinate charm is used to provide the
Corosync and Pacemaker backend HA functionality.

See [OpenStack high availability][cdg-ha-apps] in the [OpenStack Charms
Deployment Guide][cdg] for details.

> **Important**: Glance in an HA configuration must be backed by either Ceph or
  Swift.

## Glance metering

In order to do Glance metering with Ceilometer, an AMQP relation is required
e.g.

    juju deploy glance
    juju deploy rabbitmq-server
    juju deploy ceilometer-agent
    ...
    juju add-relation glance rabbitmq-server
    juju add-relation glance ceilometer-agent
    ...

## Spaces

This charm supports the use of Juju Spaces, allowing the charm to be bound to
network space configurations managed directly by Juju. This is only supported
with Juju 2.0 and above.

API endpoints can be bound to distinct network spaces supporting the network
separation of public, internal and admin endpoints.

Glance acts as a Ceph client and needs IP connectivity to Ceph monitors and
OSDs. Binding the ceph endpoint to a space can solve this problem in case
monitors and OSDs are located on a single L2 broadcast domain (if they are not,
static or dynamic routes need to be used in addition to spaces).

Access to the underlying MySQL instance can also be bound to a specific space
using the shared-db relation.

To use this feature, use the --bind option when deploying the charm:

    juju deploy glance --bind \
       "public=public-space \
        internal=internal-space \
        admin=admin-space \
        shared-db=internal-space \
        ceph=ceph-access-space"

Alternatively, these can also be provided as part of a juju native bundle
configuration:

```yaml
    glance:
      charm: cs:xenial/glance
      num_units: 1
      bindings:
        public: public-space
        admin: admin-space
        internal: internal-space
        shared-db: internal-space
        ceph: ceph-access-space
```

NOTE: Spaces must be configured in the underlying provider prior to attempting
to use them.

NOTE: Existing deployments using os-*-network configuration options will
continue to function; these options are preferred over any network space
binding provided if set.

## Policy Overrides

Policy overrides is an **advanced** feature that allows an operator to override
the default policy of an OpenStack service. The policies that the service
supports, the defaults it implements in its code, and the defaults that a charm
may include should all be clearly understood before proceeding.

> **Caution**: It is possible to break the system (for tenants and other
  services) if policies are incorrectly applied to the service.

Policy statements are placed in a YAML file. This file (or files) is then (ZIP)
compressed into a single file and used as an application resource. The override
is then enabled via a Boolean charm option.

Here are the essential commands (filenames are arbitrary):

    zip overrides.zip override-file.yaml
    juju attach-resource glance policyd-override=overrides.zip
    juju config glance use-policyd-override=true

See appendix [Policy Overrides][cdg-appendix-n] in the [OpenStack Charms
Deployment Guide][cdg] for a thorough treatment of this feature.

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-glance].

For general charm questions refer to the OpenStack [Charm Guide][cg].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[cdg-appendix-n]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-policy-overrides.html
[lp-bugs-charm-glance]: https://bugs.launchpad.net/charm-glance/+filebug
[hacluster-charm]: https://jaas.ai/hacluster
[cdg-ha-apps]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#ha-applications
