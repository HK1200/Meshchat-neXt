// SPDX-License-Identifier: MIT
export const MESHCORE_TOOL_ENTRIES = [
    {
        name: "meshcore-discovery",
        route: {
            name: "meshcore-nodes",
            query: {
                discover: "1",
            },
        },
        image: "/assets/images/tools/meshcore-discovery.svg",
        imageClass: "w-8 h-8",
        imageAlt: "Discover MeshCore nodes",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "Discover MeshCore nodes",
        description: "Find nearby repeaters, room servers and sensors. Save only the nodes you choose.",
        group: "meshcore",
    },
    {
        name: "meshcore-nodes",
        route: {
            name: "meshcore-nodes",
        },
        image: "/assets/images/tools/meshcore-nodes.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore node management",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore node management",
        description: "Routes, login, status and administrator tools for saved repeaters and room servers.",
        group: "meshcore",
    },
    {
        name: "meshcore-radio",
        route: {
            name: "meshcore-settings",
            query: {
                section: "radio2",
            },
        },
        image: "/assets/images/tools/meshcore-radio.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore radio & Radio2",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore radio & Radio2",
        description: "Independent USB/Bluetooth connection and primary or MediaMesh radio settings.",
        group: "meshcore",
    },
    {
        name: "meshcore-channels",
        route: {
            name: "meshcore-channels",
        },
        image: "/assets/images/tools/meshcore-channels.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore channels",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore channels",
        description: "Manage public and private channels, their order and notification settings.",
        group: "meshcore",
    },
    {
        name: "meshcore-contacts",
        route: {
            name: "call",
            query: {
                tab: "contacts",
                network: "meshcore",
            },
        },
        image: "/assets/images/tools/meshcore-contacts.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore contacts",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore contacts",
        description: "Search saved MeshCore users, view announces and explicitly add contacts.",
        group: "meshcore",
    },
    {
        name: "meshcore-backup",
        route: {
            name: "meshcore-settings",
            query: {
                section: "backups",
            },
        },
        image: "/assets/images/tools/meshcore-backup.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore identity & backups",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore identity & backups",
        description: "Share your MeshCore identity or review, export and import supported backups.",
        group: "meshcore",
    },
    {
        name: "meshcore-trace",
        route: {
            name: "meshcore-tools",
            params: {
                tool: "trace",
            },
        },
        image: "/assets/images/tools/meshcore-trace.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore path trace",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore path trace",
        description: "Probe a repeater path and view the returned hop signals.",
        group: "meshcore",
    },
    {
        name: "meshcore-rx",
        route: {
            name: "meshcore-tools",
            params: {
                tool: "rx",
            },
        },
        image: "/assets/images/tools/meshcore-rx.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore RX log",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore RX log",
        description: "Inspect recent radio packets, signal levels and raw frames.",
        group: "meshcore",
    },
    {
        name: "meshcore-regions",
        route: {
            name: "meshcore-tools",
            params: {
                tool: "regions",
            },
        },
        image: "/assets/images/tools/meshcore-regions.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore regions & channel scopes",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore regions & channel scopes",
        description: "Discover public regions and choose channel-only defaults and overrides.",
        group: "meshcore",
    },
    {
        name: "meshcore-noise",
        route: {
            name: "meshcore-tools",
            params: {
                tool: "noise",
            },
        },
        image: "/assets/images/tools/meshcore-noise.svg",
        imageClass: "w-8 h-8",
        imageAlt: "MeshCore noise floor",
        iconBg: "tool-card__icon bg-teal-50 dark:bg-teal-950/40",
        title: "MeshCore noise floor",
        description: "Read noise floor, last signal levels and radio airtime counters.",
        group: "meshcore",
    },
];
