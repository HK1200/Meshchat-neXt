<!-- SPDX-License-Identifier: 0BSD -->

<template>
    <div class="flex flex-1 min-w-0 h-full overflow-hidden bg-sem-canvas">
        <div class="flex-1 flex flex-col min-h-0 overflow-hidden p-4 md:p-6">
            <div class="max-w-5xl mx-auto w-full shrink-0 space-y-0 border-b border-sem-border pb-6">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <h1 class="text-2xl font-bold text-sem-fg">{{ $t("contacts.title") }}</h1>
                        <p class="text-sm text-sem-fg-muted">
                            {{ $t("contacts.description") }}
                        </p>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                        <button
                            v-if="appFeatures.reticulum || appFeatures.meshcore"
                            type="button"
                            class="secondary-chip"
                            @click="openMyIdentityDialog"
                        >
                            <MaterialDesignIcon icon-name="qrcode" class="size-4" />
                            {{ $t("contacts.share_my_identity") }}
                        </button>
                        <button
                            v-if="appFeatures.reticulum"
                            type="button"
                            class="secondary-chip justify-center px-3 sm:px-4"
                            :disabled="totalContactsCount === 0"
                            :title="$t('contacts.export_contacts')"
                            @click="exportContacts"
                        >
                            <MaterialDesignIcon icon-name="file-export" class="size-4" />
                            <span class="hidden sm:inline">{{ $t("contacts.export_contacts") }}</span>
                        </button>
                        <button
                            v-if="appFeatures.reticulum"
                            type="button"
                            class="secondary-chip justify-center px-3 sm:px-4"
                            :title="$t('contacts.import_contacts')"
                            @click="openImportDialog"
                        >
                            <MaterialDesignIcon icon-name="file-import" class="size-4" />
                            <span class="hidden sm:inline">{{ $t("contacts.import_contacts") }}</span>
                        </button>
                        <button
                            v-if="appFeatures.reticulum || appFeatures.meshcore"
                            type="button"
                            class="primary-chip hidden sm:inline-flex"
                            @click="openAddDialog"
                        >
                            <MaterialDesignIcon icon-name="plus" class="size-4" />
                            {{ $t("contacts.add_contact") }}
                        </button>
                    </div>
                </div>
            </div>

            <div class="max-w-5xl mx-auto w-full flex flex-col flex-1 min-h-0 space-y-0 pt-4">
                <div class="shrink-0 border-b border-sem-border pb-3">
                    <SearchInput
                        v-model="contactsSearch"
                        :placeholder="$t('contacts.search_placeholder')"
                        @input="onContactsSearchInput"
                    />
                </div>

                <details v-if="appFeatures.sip" class="shrink-0 border-b border-sem-border">
                    <summary class="cursor-pointer py-3 text-sm font-medium">SIP contacts</summary>
                    <SipContactBook />
                </details>
                <div class="min-w-0 flex-1 min-h-0 flex flex-col">
                    <template v-if="isLoading && contacts.length === 0">
                        <LoadingState :message="$t('contacts.loading')" />
                    </template>
                    <EmptyState
                        v-else-if="!isLoading && mergedContacts.length === 0"
                        icon="account-multiple-outline"
                        :title="$t('contacts.no_contacts')"
                        root-class="mt-4"
                    />
                    <SidebarVirtualList
                        v-else-if="mergedContacts.length >= MIN_VIRTUAL_SIDEBAR_ITEMS"
                        class="flex-1 min-h-0 divide-y divide-sem-border/60"
                        :items="mergedContacts"
                        :item-key="(item) => item.id"
                    >
                        <template #item="{ item: contact }">
                            <div
                                class="group flex cursor-default items-center gap-3 px-1 py-3 transition-colors hover:bg-sem-surface-muted/80 dark:hover:bg-sem-surface"
                                @contextmenu.prevent="openContextMenu($event, contact)"
                            >
                                <div class="shrink-0">
                                    <LxmfUserIcon
                                        :custom-image="contact.custom_image"
                                        :icon-name="contact.remote_icon ? contact.remote_icon.icon_name : ''"
                                        :icon-foreground-colour="
                                            contact.remote_icon ? contact.remote_icon.foreground_colour : ''
                                        "
                                        :icon-background-colour="
                                            contact.remote_icon ? contact.remote_icon.background_colour : ''
                                        "
                                        icon-class="size-10 sm:size-12"
                                    />
                                </div>
                                <div class="min-w-0 flex-1">
                                    <div class="font-semibold text-sem-fg flex items-center gap-1 min-w-0">
                                        <span class="truncate">{{ contact.name }}</span>
                                        <span
                                            v-if="contact.meshcore_only"
                                            class="shrink-0 text-[10px] border border-sem-border rounded px-1 font-normal"
                                            >MeshCore</span
                                        >
                                    </div>

                                    <div class="flex flex-col gap-0.5">
                                        <div
                                            v-if="contact.remote_destination_hash"
                                            class="flex items-center gap-1.5 min-w-0"
                                        >
                                            <MaterialDesignIcon
                                                icon-name="message-text-outline"
                                                class="size-4 text-sem-info shrink-0"
                                            />
                                            <button
                                                type="button"
                                                class="text-xs font-mono text-sem-fg-muted truncate hover:text-sem-accent text-left"
                                                :title="contact.remote_destination_hash"
                                                @click.stop="copyContactHash(contact.remote_destination_hash)"
                                            >
                                                {{ formatContactHash(contact.remote_destination_hash) }}
                                            </button>
                                        </div>
                                        <div
                                            v-if="contact.remote_telephony_hash"
                                            class="flex items-center gap-1.5 min-w-0"
                                        >
                                            <MaterialDesignIcon
                                                icon-name="phone-outline"
                                                class="size-4 text-sem-success shrink-0"
                                            />
                                            <button
                                                type="button"
                                                class="text-xs font-mono text-sem-fg-muted truncate hover:text-sem-accent text-left"
                                                :title="contact.remote_telephony_hash"
                                                @click.stop="copyContactHash(contact.remote_telephony_hash)"
                                            >
                                                {{ formatContactHash(contact.remote_telephony_hash) }}
                                            </button>
                                        </div>
                                        <span
                                            v-if="!contact.remote_destination_hash && !contact.remote_telephony_hash"
                                            class="text-xs font-mono text-sem-fg-muted break-all"
                                            >{{ contact.lxmf_address || contact.remote_identity_hash }}</span
                                        >
                                    </div>
                                    <SipContactLink v-if="appFeatures.sip" :contact="contact" />
                                    <MeshCoreContactNetworks
                                        v-if="appFeatures.meshcore"
                                        :key="contact.id"
                                        :contact="contact"
                                        :snapshot="mcSnapshot"
                                        @changed="mcRefresh"
                                    />
                                </div>
                                <div
                                    v-if="appFeatures.reticulum && !contact.meshcore_only"
                                    class="flex items-center gap-1 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100"
                                >
                                    <button
                                        type="button"
                                        class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-raised hover:text-sem-accent transition-colors"
                                        :title="
                                            contact.meshcore_key ? 'Message via Reticulum' : $t('contacts.send_message')
                                        "
                                        @click.stop="openConversation(contact)"
                                    >
                                        <MaterialDesignIcon icon-name="message-text-outline" class="size-5" />
                                    </button>
                                    <button
                                        type="button"
                                        class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-raised hover:text-sem-accent transition-colors"
                                        :title="$t('contacts.call_contact')"
                                        @click.stop="callContact(contact)"
                                    >
                                        <MaterialDesignIcon icon-name="phone-outline" class="size-5" />
                                    </button>
                                </div>
                                <button
                                    type="button"
                                    class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-muted hover:text-sem-fg transition-colors"
                                    :title="$t('contacts.actions')"
                                    @click.stop="openContextMenu($event, contact)"
                                >
                                    <MaterialDesignIcon icon-name="dots-vertical" class="size-5" />
                                </button>
                            </div>
                        </template>
                    </SidebarVirtualList>
                    <div v-else class="divide-y divide-sem-border/60 overflow-y-auto flex-1 min-h-0">
                        <div
                            v-for="contact in mergedContacts"
                            :key="contact.id"
                            class="group flex cursor-default items-center gap-3 px-1 py-3 transition-colors hover:bg-sem-surface-muted/80 dark:hover:bg-sem-surface"
                            @contextmenu.prevent="openContextMenu($event, contact)"
                        >
                            <div class="shrink-0">
                                <LxmfUserIcon
                                    :custom-image="contact.custom_image"
                                    :icon-name="contact.remote_icon ? contact.remote_icon.icon_name : ''"
                                    :icon-foreground-colour="
                                        contact.remote_icon ? contact.remote_icon.foreground_colour : ''
                                    "
                                    :icon-background-colour="
                                        contact.remote_icon ? contact.remote_icon.background_colour : ''
                                    "
                                    icon-class="size-10 sm:size-12"
                                />
                            </div>
                            <div class="min-w-0 flex-1">
                                <div class="font-semibold text-sem-fg flex items-center gap-1 min-w-0">
                                    <span class="truncate">{{ contact.name }}</span>
                                    <span
                                        v-if="contact.meshcore_only"
                                        class="shrink-0 text-[10px] border border-sem-border rounded px-1 font-normal"
                                        >MeshCore</span
                                    >
                                </div>

                                <div class="flex flex-col gap-0.5">
                                    <div
                                        v-if="contact.remote_destination_hash"
                                        class="flex items-center gap-1.5 min-w-0"
                                    >
                                        <MaterialDesignIcon
                                            icon-name="message-text-outline"
                                            class="size-4 text-sem-info shrink-0"
                                        />
                                        <button
                                            type="button"
                                            class="text-xs font-mono text-sem-fg-muted truncate hover:text-sem-accent text-left"
                                            :title="contact.remote_destination_hash"
                                            @click.stop="copyContactHash(contact.remote_destination_hash)"
                                        >
                                            {{ formatContactHash(contact.remote_destination_hash) }}
                                        </button>
                                    </div>
                                    <div v-if="contact.remote_telephony_hash" class="flex items-center gap-1.5 min-w-0">
                                        <MaterialDesignIcon
                                            icon-name="phone-outline"
                                            class="size-4 text-sem-success shrink-0"
                                        />
                                        <button
                                            type="button"
                                            class="text-xs font-mono text-sem-fg-muted truncate hover:text-sem-accent text-left"
                                            :title="contact.remote_telephony_hash"
                                            @click.stop="copyContactHash(contact.remote_telephony_hash)"
                                        >
                                            {{ formatContactHash(contact.remote_telephony_hash) }}
                                        </button>
                                    </div>
                                    <span
                                        v-if="!contact.remote_destination_hash && !contact.remote_telephony_hash"
                                        class="text-xs font-mono text-sem-fg-muted break-all"
                                        >{{ contact.lxmf_address || contact.remote_identity_hash }}</span
                                    >
                                </div>
                                <SipContactLink v-if="appFeatures.sip" :contact="contact" />
                                <MeshCoreContactNetworks
                                    v-if="appFeatures.meshcore"
                                    :key="contact.id"
                                    :contact="contact"
                                    :snapshot="mcSnapshot"
                                    @changed="mcRefresh"
                                />
                            </div>
                            <div
                                v-if="appFeatures.reticulum && !contact.meshcore_only"
                                class="flex items-center gap-1 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100"
                            >
                                <button
                                    type="button"
                                    class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-raised hover:text-sem-accent transition-colors"
                                    :title="
                                        contact.meshcore_key ? 'Message via Reticulum' : $t('contacts.send_message')
                                    "
                                    @click.stop="openConversation(contact)"
                                >
                                    <MaterialDesignIcon icon-name="message-text-outline" class="size-5" />
                                </button>
                                <button
                                    type="button"
                                    class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-raised hover:text-sem-accent transition-colors"
                                    :title="$t('contacts.call_contact')"
                                    @click.stop="callContact(contact)"
                                >
                                    <MaterialDesignIcon icon-name="phone-outline" class="size-5" />
                                </button>
                            </div>
                            <button
                                type="button"
                                class="p-1.5 rounded-lg text-sem-fg-muted hover:bg-sem-surface-muted hover:text-sem-fg transition-colors"
                                :title="$t('contacts.actions')"
                                @click.stop="openContextMenu($event, contact)"
                            >
                                <MaterialDesignIcon icon-name="dots-vertical" class="size-5" />
                            </button>
                        </div>
                        <div v-if="hasMoreContacts && !isLoadingMore" class="pt-2 flex justify-center">
                            <button type="button" class="secondary-chip" @click="loadMoreContacts">
                                {{ $t("contacts.load_more") }}
                            </button>
                        </div>
                        <div v-if="isLoadingMore" class="py-3 flex justify-center">
                            <div
                                class="size-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <button
            v-if="appFeatures.reticulum || appFeatures.meshcore"
            type="button"
            class="sm:hidden fixed bottom-5 right-4 z-180 flex h-14 w-14 items-center justify-center rounded-full bg-sem-action-primary text-sem-action-primary-text shadow-lg ring-1 ring-sem-border transition active:scale-95 hover:bg-sem-action-primary-hover"
            :title="$t('contacts.add_contact')"
            @click="openAddDialog"
        >
            <MaterialDesignIcon icon-name="plus" class="size-7" />
        </button>

        <!-- Contact context menu -->
        <ContextMenuPanel
            v-click-outside="{ handler: closeContextMenu, capture: true }"
            :show="contextMenu.visible"
            :x="contextMenu.x"
            :y="contextMenu.y"
            panel-class="z-210"
        >
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                @click="openConversation(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="message-text-outline" class="size-4" />
                {{ mcSnapshot.available ? "Message via Reticulum" : $t("contacts.send_message") }}
            </ContextMenuItem>
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                @click="callContact(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="phone-outline" class="size-4" />
                {{ $t("contacts.call_contact") }}
            </ContextMenuItem>
            <ContextMenuItem
                v-if="appFeatures.meshcore && contextMenu.contact?.meshcore_key"
                @click="messageMeshCore(contextMenu.contact)"
                >Message via MeshCore</ContextMenuItem
            >
            <ContextMenuDivider />
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                @click="editContactName(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="pencil-outline" class="size-4" />
                {{ $t("contacts.edit_contact") }}
            </ContextMenuItem>
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                @click="shareContact(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="share-variant" class="size-4" />
                {{ $t("contacts.share_contact") }}
            </ContextMenuItem>
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                @click="copyContactUri(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="content-copy" class="size-4" />
                {{ $t("contacts.copy_contact_uri") }}
            </ContextMenuItem>
            <ContextMenuDivider />
            <ContextMenuItem
                v-if="appFeatures.reticulum && !contextMenu.contact?.meshcore_only"
                item-class="text-sem-danger"
                @click="removeContact(contextMenu.contact)"
            >
                <MaterialDesignIcon icon-name="delete-outline" class="size-4" />
                {{ $t("contacts.remove_contact") }}
            </ContextMenuItem>
        </ContextMenuPanel>

        <!-- Add contact dialog -->
        <div
            v-if="isAddDialogOpen"
            v-escape-close="closeAddDialog"
            class="fixed inset-0 z-200 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
            @click.self="closeAddDialog"
        >
            <div
                role="dialog"
                aria-modal="true"
                class="w-full max-w-lg rounded-2xl bg-sem-surface shadow-2xl overflow-hidden"
            >
                <div class="px-5 py-4 border-b border-sem-border flex items-center justify-between">
                    <h3 class="text-lg font-bold text-sem-fg">{{ $t("contacts.add_contact") }}</h3>
                    <button
                        data-app-back
                        type="button"
                        class="text-sem-fg-muted hover:text-sem-fg"
                        @click="closeAddDialog"
                    >
                        <MaterialDesignIcon icon-name="close" class="size-5" />
                    </button>
                </div>
                <div class="p-5 space-y-4">
                    <label class="block text-xs font-semibold"
                        >Network<select v-model="newContactNetwork" class="input-field">
                            <option v-if="appFeatures.reticulum" value="rns">Reticulum</option>
                            <option v-if="appFeatures.meshcore && mcSnapshot.available" value="meshcore">
                                MeshCore
                            </option>
                        </select></label
                    >
                    <p v-if="newContactNetwork === 'meshcore'" class="text-xs text-sem-fg-muted">
                        Enter the full 64-character MeshCore public key. Adding this contact does not link it to a
                        Reticulum identity.
                    </p>
                    <div>
                        <label class="block text-xs uppercase tracking-wider font-semibold text-sem-fg-muted mb-1">
                            {{
                                newContactNetwork === "meshcore"
                                    ? "MeshCore contact name"
                                    : $t("contacts.contact_name_optional")
                            }}
                        </label>
                        <input
                            v-model="newContactName"
                            type="text"
                            class="input-field"
                            :placeholder="$t('contacts.contact_name_placeholder')"
                        />
                    </div>
                    <div>
                        <label class="block text-xs uppercase tracking-wider font-semibold text-sem-fg-muted mb-1">
                            {{ newContactNetwork === "meshcore" ? "MeshCore public key" : $t("contacts.hash_or_uri") }}
                        </label>
                        <div class="relative">
                            <input
                                v-model="newContactInput"
                                type="text"
                                class="input-field font-mono"
                                :class="cameraSupported ? 'pr-12!' : ''"
                                :placeholder="$t('contacts.hash_or_uri_placeholder')"
                                @keydown.enter.prevent="submitAddContact"
                            />
                            <button
                                v-if="cameraSupported"
                                type="button"
                                class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-8 h-8 rounded-lg text-sem-fg-muted hover:text-sem-accent hover:bg-sem-surface-raised transition"
                                :title="$t('contacts.scan_qr')"
                                @click="openScannerDialog"
                            >
                                <MaterialDesignIcon icon-name="qrcode-scan" class="size-5" />
                            </button>
                        </div>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        <button type="button" class="secondary-chip" @click="pasteFromClipboard">
                            <MaterialDesignIcon icon-name="clipboard-text-outline" class="size-4" />
                            {{ $t("contacts.paste") }}
                        </button>
                        <button v-if="cameraSupported" type="button" class="secondary-chip" @click="openScannerDialog">
                            <MaterialDesignIcon icon-name="qrcode-scan" class="size-4" />
                            {{ $t("contacts.scan_qr") }}
                        </button>
                    </div>
                </div>
                <div class="px-5 py-4 border-t border-sem-border flex justify-end gap-2">
                    <button data-app-back type="button" class="secondary-chip" @click="closeAddDialog">
                        {{ $t("common.cancel") }}
                    </button>
                    <button
                        type="button"
                        class="primary-chip"
                        :disabled="!newContactInput || isSubmitting"
                        @click="submitAddContact"
                    >
                        <MaterialDesignIcon
                            :icon-name="isSubmitting ? 'loading' : 'check'"
                            class="size-4"
                            :class="{ 'animate-spin': isSubmitting }"
                        />
                        {{ $t("contacts.add_contact") }}
                    </button>
                </div>
            </div>
        </div>

        <!-- Scanner dialog -->
        <div
            v-if="isScannerDialogOpen"
            v-escape-close="closeScannerDialog"
            class="fixed inset-0 z-220 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
            @click.self="closeScannerDialog"
        >
            <div
                role="dialog"
                aria-modal="true"
                class="w-full max-w-xl rounded-2xl bg-sem-surface shadow-2xl overflow-hidden"
            >
                <div class="px-5 py-4 border-b border-sem-border flex items-center justify-between">
                    <h3 class="text-lg font-bold text-sem-fg">{{ $t("contacts.scan_qr") }}</h3>
                    <button
                        data-app-back
                        type="button"
                        class="text-sem-fg-muted hover:text-sem-fg"
                        @click="closeScannerDialog"
                    >
                        <MaterialDesignIcon icon-name="close" class="size-5" />
                    </button>
                </div>
                <div class="p-5 space-y-3">
                    <video
                        ref="scannerVideo"
                        class="w-full rounded-xl bg-black max-h-[60vh]"
                        autoplay
                        playsinline
                        muted
                    ></video>
                    <div class="text-sm text-sem-fg-muted">
                        {{ scannerError || $t("contacts.scanner_hint") }}
                    </div>
                </div>
            </div>
        </div>

        <!-- Import contacts dialog -->
        <div
            v-if="isImportDialogOpen"
            v-escape-close="closeImportDialog"
            class="fixed inset-0 z-200 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
            @click.self="closeImportDialog"
        >
            <div
                role="dialog"
                aria-modal="true"
                class="w-full max-w-lg rounded-2xl bg-sem-surface shadow-2xl overflow-hidden"
            >
                <div class="px-5 py-4 border-b border-sem-border flex items-center justify-between">
                    <h3 class="text-lg font-bold text-sem-fg">
                        {{ $t("contacts.import_modal_title") }}
                    </h3>
                    <button
                        data-app-back
                        type="button"
                        class="text-sem-fg-muted hover:text-sem-fg"
                        @click="closeImportDialog"
                    >
                        <MaterialDesignIcon icon-name="close" class="size-5" />
                    </button>
                </div>
                <div class="p-5 space-y-4">
                    <p class="text-sm text-sem-fg-muted">
                        {{ $t("contacts.import_file_hint") }}
                    </p>
                    <input
                        ref="importFileInput"
                        type="file"
                        accept=".json,application/json"
                        class="hidden"
                        @change="onImportFileChange"
                    />
                    <button
                        type="button"
                        class="secondary-chip w-full justify-center"
                        @click="$refs.importFileInput?.click()"
                    >
                        <MaterialDesignIcon icon-name="file-upload" class="size-4" />
                        {{ $t("contacts.import_contacts") }}
                    </button>
                    <p v-if="importError" class="text-sm text-sem-danger">{{ importError }}</p>
                </div>
            </div>
        </div>

        <!-- My identity dialog -->
        <div
            v-if="isMyIdentityDialogOpen"
            v-escape-close="closeMyIdentityDialog"
            class="fixed inset-0 z-200 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs"
            @click.self="isMyIdentityDialogOpen = false"
        >
            <div
                role="dialog"
                aria-modal="true"
                class="w-full max-w-md max-h-[90dvh] overflow-y-auto rounded-2xl bg-sem-surface shadow-2xl"
            >
                <div class="px-5 py-4 border-b border-sem-border flex items-center justify-between">
                    <h3 class="text-lg font-bold text-sem-fg">
                        {{ $t("contacts.share_my_identity") }}
                    </h3>
                    <button
                        type="button"
                        class="text-sem-fg-muted hover:text-sem-fg"
                        data-app-back
                        @click="isMyIdentityDialogOpen = false"
                    >
                        <MaterialDesignIcon icon-name="close" class="size-5" />
                    </button>
                </div>
                <div class="p-5 space-y-4">
                    <div
                        v-if="appFeatures.meshcore && (mcSnapshot.available || mcSnapshot.owner)"
                        class="flex gap-2"
                        role="group"
                        aria-label="Identity network"
                    >
                        <button
                            v-if="appFeatures.reticulum"
                            type="button"
                            :class="shareNetwork === 'rns' ? 'primary-chip' : 'secondary-chip'"
                            :aria-pressed="shareNetwork === 'rns'"
                            @click="shareNetwork = 'rns'"
                        >
                            Reticulum
                        </button>
                        <button
                            v-if="appFeatures.meshcore"
                            type="button"
                            :class="shareNetwork === 'meshcore' ? 'primary-chip' : 'secondary-chip'"
                            :aria-pressed="shareNetwork === 'meshcore'"
                            @click="shareNetwork = 'meshcore'"
                        >
                            MeshCore
                        </button>
                    </div>
                    <MeshCoreIdentityShare
                        v-if="appFeatures.meshcore && shareNetwork === 'meshcore'"
                        :snapshot="mcSnapshot"
                    />
                    <template v-else-if="appFeatures.reticulum">
                        <p
                            v-if="appFeatures.meshcore && mcSnapshot.available"
                            class="text-sm font-semibold text-sem-fg text-center"
                        >
                            Reticulum identity
                        </p>
                        <div class="flex justify-center">
                            <img
                                v-if="myQrDataUrl"
                                :src="myQrDataUrl"
                                alt="Identity QR"
                                class="w-52 h-52 rounded-xl border border-sem-border bg-sem-surface"
                            />
                        </div>
                        <div class="text-xs font-mono break-all text-center text-sem-fg-muted">
                            {{ myIdentityUri }}
                        </div>
                        <div class="flex justify-center gap-2">
                            <button
                                type="button"
                                class="secondary-chip"
                                @click="copyToClipboard(myIdentityUri, $t('contacts.identity_uri_copied'))"
                            >
                                <MaterialDesignIcon icon-name="content-copy" class="size-4" />
                                {{ $t("common.copy") }}
                            </button>
                            <button type="button" class="primary-chip" @click="shareUri(myIdentityUri)">
                                <MaterialDesignIcon icon-name="share-variant" class="size-4" />
                                {{ $t("contacts.share") }}
                            </button>
                        </div>
                    </template>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { appFeatures } from "../../js/appFeatures";
import { useMeshCoreUi, combineNetworkContacts, meshcoreRoute } from "../../js/meshcoreUi";
import SipContactBook from "../sip/SipContactBook.vue";
import SipContactLink from "../sip/SipContactLink.vue";
import MeshCoreIdentityShare from "../meshcore/MeshCoreIdentityShare.vue";
import MeshCoreContactNetworks from "../meshcore/MeshCoreContactNetworks.vue";
import QRCode from "qrcode";
import Utils from "../../js/Utils";
import EmptyState from "../EmptyState.vue";
import LoadingState from "../LoadingState.vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import SearchInput from "../SearchInput.vue";
import WebSocketConnection from "../../js/WebSocketConnection";
import ToastUtils from "../../js/ToastUtils";
import DownloadUtils from "../../js/DownloadUtils";
import DialogUtils from "../../js/DialogUtils";
import { onWsEvent, offWsEvent } from "../../js/registries/wsEventRegistry";
import { apiPath, EMITTER_EVENTS, WS_EVENTS } from "../../js/constants";
import GlobalEmitter from "../../js/GlobalEmitter";
import * as announcesApi from "../../js/api/announces.js";
import * as telephoneApi from "../../js/api/telephone.js";
import {
    attachStreamToVideo,
    decodeQrFromVideo,
    describeCameraError as describeQrCameraError,
    isCameraSupported,
    startCameraStream,
} from "../../js/qrScannerUtils";

import LxmfUserIcon from "../LxmfUserIcon.vue";
import ContextMenuDivider from "../contextmenu/ContextMenuDivider.vue";
import ContextMenuItem from "../contextmenu/ContextMenuItem.vue";
import ContextMenuPanel from "../contextmenu/ContextMenuPanel.vue";
import { MIN_VIRTUAL_SIDEBAR_ITEMS } from "../../js/sidebarListVirtual.js";
import SidebarVirtualList from "../SidebarVirtualList.vue";

export default {
    name: "ContactsPage",
    components: {
        MeshCoreContactNetworks,
        MeshCoreIdentityShare,
        SipContactBook,
        SipContactLink,
        EmptyState,
        LoadingState,
        MaterialDesignIcon,
        SearchInput,
        LxmfUserIcon,
        SidebarVirtualList,
        ContextMenuDivider,
        ContextMenuItem,
        ContextMenuPanel,
    },
    setup() {
        const mc = useMeshCoreUi();
        return { appFeatures, MIN_VIRTUAL_SIDEBAR_ITEMS, mcSnapshot: mc.snapshot, mcRefresh: mc.refresh };
    },
    data() {
        return {
            contacts: [],
            contactsSearch: "",
            isLoading: false,
            isLoadingMore: false,
            searchDebounceTimeout: null,
            contactsPageSize: 30,
            contactsOffset: 0,
            totalContactsCount: 0,

            config: null,
            myIdentityUri: null,
            shareNetwork: "rns",
            myQrDataUrl: null,
            isMyIdentityDialogOpen: false,

            isAddDialogOpen: false,
            isSubmitting: false,
            newContactName: "",
            newContactInput: "",
            newContactNetwork: "rns",

            isScannerDialogOpen: false,
            scannerError: null,
            scannerStream: null,
            scannerAnimationFrame: null,
            pendingLxmaImport: false,
            lxmaImportTimeout: null,

            contextMenu: {
                visible: false,
                x: 0,
                y: 0,
                contact: null,
            },

            isImportDialogOpen: false,
            importError: null,
        };
    },
    computed: {
        cameraSupported() {
            return isCameraSupported();
        },
        hasMoreContacts() {
            return this.contacts.length < this.totalContactsCount;
        },
        mergedContacts() {
            const map = new Map();
            for (const c of appFeatures.reticulum ? this.contacts : []) {
                const key = c.remote_identity_hash || `contact:${c.id}`;
                if (!map.has(key)) {
                    map.set(key, { ...c });
                } else {
                    const existing = map.get(key);
                    // Merge fields so both LXMF and LXST addresses are visible
                    existing.lxmf_address = existing.lxmf_address || c.lxmf_address;
                    existing.lxst_address = existing.lxst_address || c.lxst_address;
                    existing.remote_destination_hash = existing.remote_destination_hash || c.remote_destination_hash;
                    existing.remote_telephony_hash = existing.remote_telephony_hash || c.remote_telephony_hash;
                    existing.remote_identity_hash = existing.remote_identity_hash || c.remote_identity_hash;
                }
            }
            return combineNetworkContacts(Array.from(map.values()), appFeatures.meshcore ? this.mcSnapshot : {}).filter(
                (contact) =>
                    `${contact.name} ${contact.meshcore_key || ""}`
                        .toLowerCase()
                        .includes(this.contactsSearch.toLowerCase())
            );
        },
    },
    beforeUnmount() {
        offWsEvent(WS_EVENTS.LXM_INGEST_URI_RESULT, this.onLxmIngestUriResult);
        GlobalEmitter.off(EMITTER_EVENTS.IDENTITY_SWITCHED, this.onIdentitySwitched);
        clearTimeout(this.lxmaImportTimeout);

        this.stopScanner();
        if (this.searchDebounceTimeout) {
            clearTimeout(this.searchDebounceTimeout);
        }
    },
    async mounted() {
        onWsEvent(WS_EVENTS.LXM_INGEST_URI_RESULT, this.onLxmIngestUriResult);
        GlobalEmitter.on(EMITTER_EVENTS.IDENTITY_SWITCHED, this.onIdentitySwitched);
        await this.getConfig();
        await this.getContacts();
    },
    methods: {
        messageMeshCore(contact) {
            this.closeContextMenu();
            this.$router.push(meshcoreRoute(contact.meshcore_key));
        },
        async onIdentitySwitched() {
            // Contacts, the share URI, and its QR all belong to the old
            // identity. Drop them before the new identity's data lands.
            this.contacts = [];
            this.totalContactsCount = 0;
            this.myQrDataUrl = null;
            this.myIdentityUri = null;
            this.closeContextMenu();
            await this.getConfig();
            await this.getContacts();
        },
        async getConfig() {
            try {
                const response = await window.api.get(apiPath("/config"));
                this.config = response.data.config;
                this.myIdentityUri = this.buildMyIdentityUri();
                if (this.myIdentityUri) {
                    this.myQrDataUrl = await QRCode.toDataURL(this.myIdentityUri, { margin: 1, scale: 6 });
                }
            } catch (e) {
                console.log(e);
            }
        },
        buildMyIdentityUri() {
            if (!this.config?.lxmf_address_hash) return null;
            if (this.config?.identity_public_key) {
                return `lxma://${this.config.lxmf_address_hash}:${this.config.identity_public_key}`;
            }
            // Bare hash: lxma:// and lxmf:// are not universally parsed;
            // every LXMF client accepts the 32-hex form.
            return this.config.lxmf_address_hash;
        },
        async getContacts(append = false) {
            if (append) {
                this.isLoadingMore = true;
            } else {
                this.isLoading = true;
                this.contactsOffset = 0;
            }
            try {
                const response = await telephoneApi.listContacts({
                    params: {
                        search: this.contactsSearch || undefined,
                        limit: this.contactsPageSize,
                        offset: this.contactsOffset,
                    },
                });
                const list = response.data?.contacts ?? (Array.isArray(response.data) ? response.data : []);
                this.totalContactsCount = response.data?.total_count ?? list.length;
                if (append) {
                    this.contacts = [...this.contacts, ...list];
                } else {
                    this.contacts = list;
                }
                this.contactsOffset += list.length;
            } catch (e) {
                console.log(e);
                ToastUtils.error(this.$t("contacts.failed_load_contacts"));
            } finally {
                this.isLoading = false;
                this.isLoadingMore = false;
            }
        },
        loadMoreContacts() {
            if (this.isLoadingMore || !this.hasMoreContacts) return;
            this.getContacts(true);
        },
        onContactsSearchInput() {
            if (this.searchDebounceTimeout) clearTimeout(this.searchDebounceTimeout);
            this.searchDebounceTimeout = setTimeout(() => {
                this.getContacts();
            }, 250);
        },
        openAddDialog() {
            this.newContactName = "";
            this.newContactInput = "";
            this.newContactNetwork = appFeatures.reticulum ? "rns" : "meshcore";
            this.pendingLxmaImport = false;
            this.isAddDialogOpen = true;
        },
        openImportDialog() {
            this.importError = null;
            this.isImportDialogOpen = true;
        },
        closeImportDialog() {
            this.isImportDialogOpen = false;
            this.importError = null;
        },
        onImportFileChange(event) {
            const file = event.target.files?.[0];
            if (!file) return;
            this.importError = null;
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const json = JSON.parse(e.target?.result || "{}");
                    const contacts = json.contacts ?? (Array.isArray(json) ? json : []);
                    if (!Array.isArray(contacts) || contacts.length === 0) {
                        this.importError = this.$t("contacts.import_failed");
                        return;
                    }
                    this.importContacts(contacts);
                } catch {
                    this.importError = this.$t("contacts.import_failed");
                }
            };
            reader.readAsText(file);
            event.target.value = "";
        },
        async importContacts(contacts) {
            try {
                const response = await window.api.post(apiPath("/telephone/contacts/import"), {
                    contacts,
                });
                const added = response.data?.added ?? 0;
                ToastUtils.success(this.$t("contacts.import_success", { added }));
                this.closeImportDialog();
                await this.getContacts();
            } catch (e) {
                this.importError = e?.response?.data?.message || this.$t("contacts.import_failed");
            }
        },
        async exportContacts() {
            try {
                const response = await window.api.get(apiPath("/telephone/contacts/export"));
                const contacts = response.data?.contacts ?? [];
                const blob = new Blob([JSON.stringify({ contacts }, null, 2)], {
                    type: "application/json",
                });
                await DownloadUtils.downloadFile("contacts_export.json", blob);
                ToastUtils.success(this.$t("contacts.export_success"));
            } catch (e) {
                ToastUtils.error(e?.response?.data?.message || this.$t("contacts.export_failed"));
            }
        },
        closeAddDialog() {
            this.isAddDialogOpen = false;
            this.pendingLxmaImport = false;
        },
        openMyIdentityDialog() {
            this.shareNetwork = appFeatures.reticulum ? "rns" : "meshcore";
            this.isMyIdentityDialogOpen = true;
        },
        closeMyIdentityDialog() {
            this.isMyIdentityDialogOpen = false;
        },
        parseLxmaUri(input) {
            const normalized = input.trim();
            const match = normalized.match(/^lxma:\/\/([0-9a-f]{32}):([0-9a-f]{64}|[0-9a-f]{128})$/i);
            if (!match) return null;
            return {
                destinationHash: match[1].toLowerCase(),
                publicKeyHex: match[2].toLowerCase(),
                normalizedUri: `lxma://${match[1].toLowerCase()}:${match[2].toLowerCase()}`,
            };
        },
        extractDestinationHash(input) {
            const raw = input.trim().toLowerCase();
            if (/^[0-9a-f]{32}$/.test(raw)) return raw;
            const lxmfMatch = raw.match(/^lxmf:\/\/([0-9a-f]{32})$/);
            if (lxmfMatch) return lxmfMatch[1];
            const lxmMatch = raw.match(/^lxm:\/\/([0-9a-f]{32})$/);
            if (lxmMatch) return lxmMatch[1];
            return null;
        },
        async submitAddContact() {
            if (this.newContactNetwork === "meshcore") {
                if (this.isSubmitting) return;
                this.isSubmitting = true;
                try {
                    await window.api.post(apiPath("/meshcore/contact-add"), {
                        peer: this.newContactInput.trim().toLowerCase(),
                        name: this.newContactName.trim(),
                        expected_owner: this.mcSnapshot.owner,
                    });
                    await this.mcRefresh();
                    this.closeAddDialog();
                } catch {
                    ToastUtils.error(
                        "Could not add MeshCore contact. Check the full public key, name, and radio connection."
                    );
                } finally {
                    this.isSubmitting = false;
                }
                return;
            }
            if (!this.newContactInput || this.isSubmitting) return;
            this.isSubmitting = true;
            try {
                const lxmaData = this.parseLxmaUri(this.newContactInput);
                if (lxmaData) {
                    const sent = WebSocketConnection.send(
                        JSON.stringify({
                            type: "lxm.ingest_uri",
                            uri: lxmaData.normalizedUri,
                        })
                    );
                    if (!sent) {
                        this.isSubmitting = false;
                        ToastUtils.error(this.$t("contacts.failed_add_contact"));
                        return;
                    }
                    this.pendingLxmaImport = true;
                    ToastUtils.info(this.$t("contacts.importing_lxma"));
                    // No result arrives when the request is dropped, so bound
                    // the wait instead of leaving the submit button spinning.
                    clearTimeout(this.lxmaImportTimeout);
                    this.lxmaImportTimeout = setTimeout(() => {
                        if (this.pendingLxmaImport) {
                            this.pendingLxmaImport = false;
                            this.isSubmitting = false;
                        }
                    }, 30000);
                    return;
                }

                const destinationHash = this.extractDestinationHash(this.newContactInput);
                if (!destinationHash) {
                    ToastUtils.error(this.$t("contacts.invalid_contact_input"));
                    return;
                }

                const existing = await window.api.get(apiPath(`/telephone/contacts/check/${destinationHash}`));
                if (existing.data?.id) {
                    ToastUtils.info(this.$t("contacts.contact_already_exists"));
                    return;
                }

                await window.api.post(apiPath("/telephone/contacts"), {
                    name: this.newContactName?.trim() || `Contact ${destinationHash.slice(0, 8)}`,
                    lxmf_address: destinationHash,
                });
                ToastUtils.success(this.$t("contacts.contact_added"));
                this.closeAddDialog();
                await this.getContacts();
            } catch (e) {
                ToastUtils.error(e.response?.data?.message || this.$t("contacts.failed_add_contact"));
            } finally {
                this.isSubmitting = false;
            }
        },
        async onLxmIngestUriResult(json) {
            if (!this.pendingLxmaImport) {
                return;
            }
            this.pendingLxmaImport = false;
            this.isSubmitting = false;
            clearTimeout(this.lxmaImportTimeout);
            if (json.status === "success" && json.ingest_type === "lxma_contact") {
                ToastUtils.success(json.message || this.$t("contacts.contact_added"));
                this.closeAddDialog();
                await this.getContacts();
            } else if (json.status === "error") {
                ToastUtils.error(json.message || this.$t("contacts.failed_add_contact"));
            }
        },
        async removeContact(contact) {
            this.closeContextMenu();
            if (!contact?.id) return;
            const duplicates = this.contacts.filter((c) => c.name === contact.name && c.id !== contact.id);
            const confirmMsg =
                duplicates.length > 0
                    ? this.$t("contacts.remove_duplicates_confirm", {
                          count: duplicates.length,
                          name: contact.name,
                      })
                    : this.$t("contacts.remove_contact_confirm");
            if (!(await DialogUtils.confirm(confirmMsg))) return;
            try {
                const ids = [contact.id, ...duplicates.map((c) => c.id)];
                for (const id of ids) {
                    await window.api.delete(apiPath(`/telephone/contacts/${id}`));
                }
                ToastUtils.success(this.$t("contacts.contact_removed"));
                await this.getContacts();
            } catch {
                ToastUtils.error(this.$t("contacts.failed_remove_contact"));
            }
        },
        async editContactName(contact) {
            this.closeContextMenu();
            if (!contact?.id) return;
            const entered = await DialogUtils.prompt(this.$t("contacts.enter_contact_name"), contact.name);
            if (entered == null) return;
            const name = String(entered).trim();
            if (!name || name === contact.name) return;
            try {
                const duplicates = this.contacts.filter((c) => c.name === contact.name && c.id !== contact.id);
                const ids = [contact.id, ...duplicates.map((c) => c.id)];
                for (const id of ids) {
                    await window.api.patch(apiPath(`/telephone/contacts/${id}`), { name });
                }
                const allContacts = [contact, ...duplicates];
                for (const c of allContacts) {
                    const destHash = c.remote_destination_hash || c.lxmf_address || c.remote_identity_hash;
                    if (destHash) {
                        await window.api.post(apiPath(`/destination/${destHash}/custom-display-name/update`), {
                            display_name: name,
                        });
                    }
                }
                ToastUtils.success(this.$t("contacts.contact_updated"));
                await this.getContacts();
            } catch {
                ToastUtils.error(this.$t("contacts.failed_update_contact"));
            }
        },
        openConversation(contact) {
            this.closeContextMenu();
            const hash = contact.remote_destination_hash || contact.lxmf_address || contact.remote_identity_hash;
            if (!hash) return;
            this.$router.push({ name: "messages", params: { destinationHash: hash } });
        },
        callContact(contact) {
            this.closeContextMenu();
            const hash =
                contact.remote_telephony_hash || contact.remote_destination_hash || contact.remote_identity_hash;
            if (!hash) return;
            this.$router.push({ name: "call", query: { destination_hash: hash, tab: "phone" } });
        },
        openContextMenu(event, contact) {
            this.contextMenu.visible = true;
            this.contextMenu.contact = contact;
            this.contextMenu.x = event.clientX;
            this.contextMenu.y = event.clientY;
        },
        closeContextMenu() {
            this.contextMenu.visible = false;
            this.contextMenu.contact = null;
        },
        async fetchContactLxmaUri(contact) {
            const destinationHash = (contact?.lxmf_address || contact?.remote_identity_hash || "").toLowerCase();
            if (!/^[0-9a-f]{32}$/.test(destinationHash)) return null;
            try {
                const response = await announcesApi.listAnnounces({
                    params: {
                        destination_hash: destinationHash,
                        limit: 1,
                    },
                });
                const announce = response.data?.announces?.[0];
                const publicKeyBase64 = announce?.identity_public_key;
                if (!publicKeyBase64) return null;
                const binary = atob(publicKeyBase64);
                const publicKeyHex = Array.from(binary)
                    .map((c) => c.charCodeAt(0).toString(16).padStart(2, "0"))
                    .join("");
                if (publicKeyHex.length !== 64 && publicKeyHex.length !== 128) return null;
                return `lxma://${destinationHash}:${publicKeyHex}`;
            } catch {
                return null;
            }
        },
        async copyContactUri(contact) {
            this.closeContextMenu();
            const lxmaUri = await this.fetchContactLxmaUri(contact);
            if (lxmaUri) {
                await this.copyToClipboard(lxmaUri, this.$t("contacts.contact_uri_copied"));
                return;
            }

            const destinationHash = contact?.lxmf_address || contact?.remote_identity_hash;
            if (destinationHash) {
                // Bare hash for maximum client compatibility. lxmf:// is not
                // accepted by every LXMF client.
                await this.copyToClipboard(destinationHash, this.$t("contacts.contact_uri_copied"));
            } else {
                ToastUtils.error(this.$t("contacts.failed_build_contact_uri"));
            }
        },
        formatContactHash(hash) {
            return Utils.formatDestinationHash(hash);
        },
        async copyContactHash(hash) {
            if (!hash) {
                return;
            }
            await this.copyToClipboard(hash, this.$t("common.copied"));
        },
        async shareContact(contact) {
            this.closeContextMenu();
            const lxmaUri = await this.fetchContactLxmaUri(contact);
            const destinationHash = contact?.lxmf_address || contact?.remote_identity_hash;
            // Bare hash fallback: lxmf:// is not accepted by every LXMF
            // client, while the 32-hex form is.
            const fallback = destinationHash || null;
            const uri = lxmaUri || fallback;
            if (!uri) {
                ToastUtils.error(this.$t("contacts.failed_build_contact_uri"));
                return;
            }
            await this.shareUri(uri);
        },
        async shareUri(uri) {
            try {
                if (navigator.share) {
                    await navigator.share({
                        title: this.$t("contacts.share"),
                        text: uri,
                    });
                    return;
                }
            } catch {
                // ignore and fallback to clipboard
            }
            await this.copyToClipboard(uri, this.$t("contacts.contact_uri_copied"));
        },
        async copyToClipboard(value, successMessage) {
            try {
                await navigator.clipboard.writeText(value);
                ToastUtils.success(successMessage || this.$t("common.copied"));
            } catch {
                ToastUtils.error(this.$t("common.failed_to_copy"));
            }
        },
        async pasteFromClipboard() {
            try {
                this.newContactInput = await navigator.clipboard.readText();
            } catch {
                ToastUtils.error(this.$t("messages.failed_read_clipboard"));
            }
        },
        async openScannerDialog() {
            this.isScannerDialogOpen = true;
            this.scannerError = null;
            await this.$nextTick();
            await this.startScanner();
        },
        async startScanner() {
            if (!this.cameraSupported) {
                this.scannerError = this.$t("contacts.camera_not_supported");
                return;
            }
            try {
                const stream = await startCameraStream();
                if (!stream.getVideoTracks().length) {
                    this.scannerError = this.$t("contacts.camera_not_found");
                    stream.getTracks().forEach((track) => track.stop());
                    return;
                }
                this.scannerStream = stream;
                const video = this.$refs.scannerVideo;
                if (!(await attachStreamToVideo(stream, video))) {
                    return;
                }
                this.detectQrLoop();
            } catch (e) {
                this.scannerError = this.describeCameraError(e);
            }
        },
        detectQrLoop() {
            if (!this.isScannerDialogOpen) return;
            const video = this.$refs.scannerVideo;
            decodeQrFromVideo(video)
                .then((qr) => {
                    if (!this.isScannerDialogOpen) {
                        return;
                    }
                    if (qr) {
                        this.newContactInput = qr;
                        this.closeScannerDialog();
                        ToastUtils.success(this.$t("contacts.qr_scanned"));
                        return;
                    }
                    this.scannerAnimationFrame = requestAnimationFrame(() => this.detectQrLoop());
                })
                .catch(() => {
                    if (this.isScannerDialogOpen) {
                        this.scannerAnimationFrame = requestAnimationFrame(() => this.detectQrLoop());
                    }
                });
        },
        stopScanner() {
            if (this.scannerAnimationFrame) {
                cancelAnimationFrame(this.scannerAnimationFrame);
                this.scannerAnimationFrame = null;
            }
            if (this.scannerStream) {
                this.scannerStream.getTracks().forEach((track) => track.stop());
                this.scannerStream = null;
            }
        },
        closeScannerDialog() {
            this.isScannerDialogOpen = false;
            this.stopScanner();
        },
        describeCameraError(error) {
            return describeQrCameraError(error, {
                permissionDenied: this.$t("contacts.camera_permission_denied"),
                notFound: this.$t("contacts.camera_not_found"),
                failed: this.$t("contacts.camera_failed"),
            });
        },
    },
};
</script>

<style scoped>
@reference "../../style.css";
.glass-card {
    @apply bg-sem-glass backdrop-blur-sm border border-sem-border rounded-2xl shadow-xs p-4;
}

.input-field {
    @apply bg-sem-surface border border-sem-border text-sm rounded-xl focus:ring-2 focus:ring-sem-focus focus:border-sem-accent block w-full p-2.5 text-sem-fg transition;
}

.primary-chip {
    @apply inline-flex items-center gap-1 rounded-xl bg-sem-action-primary hover:bg-sem-action-primary-hover text-sem-action-primary-text px-3 py-2 text-xs font-semibold transition disabled:opacity-60;
}

.secondary-chip {
    @apply inline-flex items-center gap-1 rounded-xl bg-sem-surface-muted hover:bg-sem-surface-raised text-sem-fg-secondary px-3 py-2 text-xs font-semibold transition;
}
</style>
