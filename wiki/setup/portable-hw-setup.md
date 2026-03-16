# Portable Hardware Setup: Stable Kubernetes Networking with Tailscale and Headscale

## Problem Statement

When the IP addresses of devices hosting DigitalTwin and agent services change frequently, Kubernetes (K3S) cluster recovery becomes difficult and requires manual execution of recovery scripts to restore the cluster to a healthy state. This causes disruption to service operation.

Additionally, the K3S CoreDNS component resets to its defaults unless a custom ConfigMap is applied, which causes connectivity issues with peer devices. When running under Tailscale, additional CoreDNS configuration is also required to allow internet access over the physical Ethernet interface.

## Solution

By leveraging the OS virtual LAN layer, K3S can be bound to a virtual IP address that never changes. Physical network interfaces can then be freely reassigned for machine and peer connections without affecting the Kubernetes cluster.

A Tailscale agent on each edge device, connected to a self-hosted virtual LAN router called **Headscale**, provides this capability. As open-source, lightweight components, Tailscale creates a virtual NIC (`tailscale0`) that serves as the stable interface for hosting K3S.

---

## Setup Procedure

### Step 1 — Install Ubuntu 22.04 on IFF Edge Devices

Install Ubuntu 22.04 (Server or Desktop edition) on all IFF edge devices. Enable SSH access manually if it is not enabled by default.

### Step 2 — Install Headscale on a Local Jump Server

Install Headscale on a local jump server to act as the virtual LAN router for the edge devices.

Reference: [Headscale installation guide for Debian/Ubuntu](https://headscale.net/stable/setup/install/official/#using-packages-for-debianubuntu-recommended)

### Step 3 — Create a Headscale User and Generate an Auth Key

```bash
headscale users create iff
headscale users list
headscale preauthkeys create --user <USER_ID>
```

### Step 4 — Install Tailscale on IFF Edge Devices

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

### Step 5 — Join the Headscale Server

Connect each edge device to the Headscale server. The Headscale URL follows the pattern `http://<HEADSCALE_SERVER_IP>:8080`.

```bash
tailscale up --login-server <YOUR_HEADSCALE_URL> --authkey <YOUR_AUTH_KEY>

tailscale set --accept-dns=false
```

### Step 6 — Verify the Tailscale Virtual Interface

Once the edge devices have joined the Headscale server, a new virtual network interface (`tailscale0`) will appear with a stable virtual IP address.

> **Note:** After this point, edge devices no longer require direct communication with the Headscale server.

Example interface output:

```
tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
```

### Step 7 — Install K3S Bound to the Tailscale Interface

Install K3S on each edge device, binding it to the `tailscale0` interface and its corresponding virtual IP address.

```bash
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_VERSION="v1.31.0+k3s1" \
  sh -s - server \
    --cluster-init \
    --node-name "iff-edge-device-1" \
    --node-ip "100.64.0.2" \
    --advertise-address "100.64.0.2" \
    --flannel-iface "tailscale0" \
    --etcd-snapshot-schedule-cron "0 */5 * * *" \
    --etcd-snapshot-retention 5 \
    --etcd-snapshot-dir "/var/lib/rancher/k3s/server/db/snapshots"
```

### Step 8 — Configure CoreDNS with a Custom ConfigMap

> **Important:** Apply the custom CoreDNS ConfigMap on both the DigitalTwin Server and Agent Gateways, then restart the CoreDNS pods.

The ConfigMap template is the same for both node types. The only difference is the value assigned to `$INGRESS_IP`.

#### Digital Twin Server

> Requires internet access during operation.

Set `$INGRESS_IP` to the **Tailscale-provided virtual IP address** of the server.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns-custom
  namespace: kube-system
data:
  customhosts.override: |
    template IN A {
      match (keycloak|ngsild|mqtt|alerta|pgrest)\.local\.$
      answer "{{ .Name }} 60 IN A $INGRESS_IP"
      fallthrough
    }
  forward.override: |
    forward . 1.1.1.1 8.8.8.8 {
      policy sequential
    }
```

#### Agent Gateways

> Does not require internet access, but must be able to reach the DigitalTwin Server and connected machines via the physical Ethernet network.

Set `$INGRESS_IP` to the **physical (Ethernet) IP address** of the DigitalTwin Server.

Use the same ConfigMap structure as above, substituting the appropriate `$INGRESS_IP` value.

### Step 9 — Deploy Services

K3S-enabled devices are now ready to be provisioned with DigitalTwin services, or imported into a cluster management system for GitOps-based service deployments.

