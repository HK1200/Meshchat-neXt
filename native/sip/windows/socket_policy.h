/* SPDX-License-Identifier: 0BSD */
/* Force-include only in libre's socket-creating sources on Windows. */
#ifndef NEXT_WINDOWS_SOCKET_POLICY_H
#define NEXT_WINDOWS_SOCKET_POLICY_H
#include <winsock2.h>
SOCKET WSAAPI next_windows_socket(int family, int type, int protocol);
#define socket(family,type,protocol) next_windows_socket(family,type,protocol)
#endif
