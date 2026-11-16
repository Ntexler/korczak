/* Derived from https://github.com/izhikevich/SNN (commit 74225a5), MIT License, (c) 2025 Eugene Izhikevich; see LICENSE-izhikevich-SNN.
   Changes: model untouched except shared positional encodings for Hogwild threads; new harness (data split, eval, threads). */
/* SNN transformer architecture in pure C. */
/* Based on Spiking Manifesto (Izhikevich 2025) */
/* The code strives for simplicity, not efficiency. */
/* Eugene Izhikevich, October 2025 */

#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <time.h>
#include <math.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <pthread.h>
#include <stdatomic.h>

#define FILE_NAME "loss.csv"    // saves validation loss values during training

#define CONTEXT_SIZE            32
#define VOCAB_SIZE              256
#define EMBEDDING_DIM           32
#define POSITIONAL_DIM          4     
#define NUM_LAYERS              6
#define NUM_HEADS               4

#define N_T                     16      
#define N_C                     6     


#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define sign(x) (x > 0 ? 1 : -1)        // zero has "minus" sign
#define U(x) ( 0.5/(1+fabs(x)) )        // not used; here for reference
#define Up(x) (-0.5*sign(x)/(1+fabs(x))/(1+fabs(x))) 

#define LEARNING_RATE  (MIN( 1 /sqrt(1+t), t/(4000.0f)/sqrt(4000) )) // Adam learning rate scheduler
__thread float learning_rate;
#define TESTING_LENGTH 10000


// ----------------------------------------------------------------------------
// Spiking model

typedef struct {
    int a[N_C];     
    int b[N_C];
} Anchors;

typedef struct {
    int y_dim;       // dimension of the output y
    float* S[N_T];   // synaptic values (table_size, y_dim), i.e., (,j,k) in the paper
    Anchors anchors[N_T];    
} LUT;

typedef struct {
    int r_min[N_T];
    float u_min[N_T];
    int j[N_T];      // j = H_i(x)
} LUTcache;

typedef struct {
    LUT V;
    LUTcache V_cache[CONTEXT_SIZE];

    float (*Positional_encoding)[N_T][POSITIONAL_DIM];  // position -> embedding (shared)
    LUTcache PE_cache[CONTEXT_SIZE];

} AttentionHead;

typedef struct {
    float Token_embedder[VOCAB_SIZE][EMBEDDING_DIM];    // token -> embedding
    int tokens[CONTEXT_SIZE+1];                         // currrent training sample

    float z[CONTEXT_SIZE][EMBEDDING_DIM];               // resnet connections: each layer adds to z
    
    LUT FFN[NUM_LAYERS];
    LUTcache FFN_cache[NUM_LAYERS][CONTEXT_SIZE];

    AttentionHead head[NUM_LAYERS][NUM_HEADS];

    LUT unembedder;
    LUTcache unembedder_vars[CONTEXT_SIZE];

    float output[CONTEXT_SIZE][VOCAB_SIZE];             // the output becomes the error gradient in the backward pass 
} Model;



void softmax(float* x, int size, float temperature) {
    // find max value (for numerical stability)
    float max_val = x[0];
    for (int i = 1; i < size; i++) {
        if (x[i] > max_val) {
            max_val = x[i];
        }
    }
    // exp and sum
    float sum = 0.0f;
    for (int i = 0; i < size; i++) {
        x[i] = expf( (x[i] - max_val) / temperature );
        sum += x[i];
    }
    // normalize
    for (int i = 0; i < size; i++) {
        x[i] /= sum;
    }
}

float vector_multiply(float* vector1, float* vector2, int size) {
    float result = 0;
    for (int i = 0; i < size; i++) {
        result += vector1[i] * vector2[i];
    }
    return result;
}

void random_vector(float* vector, int size, float scale) {
    for (int i = 0; i < size; i++) {
        vector[i] = scale * 2*( (float)rand()/RAND_MAX - 0.5);
    }
}

int sample(float* probabilities, int n) {
    // sample index from probabilities (they must sum to 1!)
    float coin = (float)rand() / RAND_MAX;
    float cdf = 0.0f;
    for (int i = 0; i < n; i++) {
        cdf += probabilities[i];
        if (coin < cdf) {
            return i;
        }
    }
    return n - 1; // in case of rounding errors
}

void fill_vector_with_random_intergers(int* vector, int N, int Max_value) {

    for (int i = 0; i < N; i++) {   
        vector[i] = rand()%Max_value;
    }
}

void fill_vector_with_random_intergers_different_from_vector2(int* vector, int* vector2, int N, int Max_value) {

    for (int i = 0; i < N; i++) {   
        do {
            vector[i] = rand()%Max_value;
        } while (vector2[i] == vector[i]);
    }
}

void build_LUT(LUT* lut, int total_n_c, int y_dim) {

    lut->y_dim = y_dim;
    for (int i = 0; i < N_T; i++) {
        fill_vector_with_random_intergers(lut->anchors[i].a, N_C, EMBEDDING_DIM);
        fill_vector_with_random_intergers_different_from_vector2(lut->anchors[i].b, lut->anchors[i].a, N_C, EMBEDDING_DIM);
        lut->S[i] = (float*)calloc(  (1 << total_n_c) * y_dim, sizeof(float));
        memset(lut->S[i], 0, (1 << total_n_c) * y_dim * sizeof(float));
    }
}

void free_LUT(LUT* lut) {

    for (int i = 0; i < N_T; i++) {
        free(lut->S[i]);
    }
}

void cache_index(LUT* lut, LUTcache* cache, float* x) {

    for (int i = 0; i < N_T; i++) { 
        cache->j[i] = 0;
        cache->u_min[i] = INFINITY;

        for (int r = 0; r < N_C; r++) { // loop over all comparisons per table
            float u = x[lut->anchors[i].a[r]] - x[lut->anchors[i].b[r]];
            if (u > 0) {
                cache->j[i] |= (1 << r); // concatenation 
            }
            if (fabs(u) < fabs(cache->u_min[i])) {
                cache->r_min[i] = r;
                cache->u_min[i] = u;
            }
        }
    }
}

void cache_PE_index(LUTcache* cache, float u[N_T][POSITIONAL_DIM]) {

    for (int i = 0; i < N_T; i++) { 
        cache->j[i] = 0;
        cache->u_min[i] = INFINITY;

        for (int r = 0; r < POSITIONAL_DIM; r++) { 
            if (u[i][r] > 0) {          // No anchor neurons; just a comparison with 0; works best for small POSITIONAL_DIM.
                cache->j[i] |= (1 << r);
            }
            if (fabs(u[i][r]) < fabs(cache->u_min[i])) {
                cache->r_min[i] = r;
                cache->u_min[i] = u[i][r];
            }
        }
    }
}

void LUT_forward(LUT* lut, LUTcache* cache, float* y) {

    // main loop in the forward pass
    for (int i = 0; i < N_T; i++) { 
        for (int k = 0; k < lut->y_dim; k++) {
            y[k] += lut->S[i][  cache->j[i] * lut->y_dim + k ];
        }
    }
}

#define BACKWARD_UPDATE(cache, gradient) \
    do { \
        float gi = 0; \
        for (int k = 0; k < lut->y_dim; k++) { \
            gi += y_gradient[k] * ( lut->S[i][ jbar + k ] - lut->S[i][ j + k ] ); \
        } \
        float v = gi * Up(cache->u_min[i]); \
        gradient[lut->anchors[i].a[cache->r_min[i]]] += v; \
        gradient[lut->anchors[i].b[cache->r_min[i]]] -= v; \
    } while (0)
//

void LUT_backward(LUT* lut, LUTcache* cache, float* x_gradient, float* y_gradient) {

    for (int i = 0; i < N_T; i++) {
        int j = cache->j[i] * lut->y_dim;
        // flip the bit number r_min 
        int jbar = ( cache->j[i] ^ (1 << cache->r_min[i]) ) * lut->y_dim;
        
        BACKWARD_UPDATE(cache, x_gradient);

        for (int k = 0; k < lut->y_dim; k++) {
            lut->S[i][ j + k] -= learning_rate * y_gradient[k];
        }
    }
}

#define CONCATENATE(Q, P, PE) ((((Q) << (N_C+POSITIONAL_DIM)) | ((P) << POSITIONAL_DIM) | (PE)) * lut->y_dim)


void concatenated_LUT_forward(LUT* lut,  LUTcache* cacheQ, LUTcache* cacheK, LUTcache* cachePE, float* y) {

    for (int i = 0; i < N_T; i++) { 
        int j = CONCATENATE( cacheQ->j[i], cacheK->j[i], cachePE->j[i] );
        for (int k = 0; k < lut->y_dim; k++) {
            y[k] += lut->S[i][ j + k ];
        }
    }
}

void concatenated_LUT_backward(LUT* lut, LUTcache* cacheQ, LUTcache* cacheK, LUTcache* cachePE, float* x_gradientQ, float* x_gradientK, float PE_grad[N_T][POSITIONAL_DIM], float* y_gradient) {

    for (int i = 0; i < N_T; i++) {

        int j = CONCATENATE( cacheQ->j[i], cacheK->j[i], cachePE->j[i] );
    
        if ( fabs(cacheQ->u_min[i]) < fabs(cacheK->u_min[i]) ) {
            int jbar  = CONCATENATE( cacheQ->j[i] ^ (1 << cacheQ->r_min[i]), cacheK->j[i], cachePE->j[i] ); // only jQ is flipped
            BACKWARD_UPDATE(cacheQ, x_gradientQ);
        }
        else {
            int jbar  = CONCATENATE( cacheQ->j[i], cacheK->j[i] ^ (1 << cacheK->r_min[i]), cachePE->j[i] ); // only jP is flipped
            BACKWARD_UPDATE(cacheK, x_gradientK);
        }

        if ( fabs(cachePE->u_min[i]) < fabs(cacheQ->u_min[i]) && fabs(cachePE->u_min[i]) < fabs(cacheK->u_min[i]) ) {
            int jbarPE = CONCATENATE( cacheQ->j[i], cacheK->j[i], cachePE->j[i] ^ (1 << cachePE->r_min[i]) ); // only jPE is flipped
            float giPE = 0;
            for (int k = 0; k < lut->y_dim; k++) {
                giPE += y_gradient[k] * ( lut->S[i][ jbarPE + k ] - lut->S[i][ j + k ] );
            }
            float deltaPE = giPE * Up(cachePE->u_min[i]);
            PE_grad[i][cachePE->r_min[i]] += deltaPE; // No anchor neurons; just a comparison with 0.
        }

        for (int k = 0; k < lut->y_dim; k++) {
            lut->S[i][ j + k] -= learning_rate * y_gradient[k];
        }
    }
}

void build_Model(Model* m) {

    random_vector(m->Token_embedder[0], VOCAB_SIZE*EMBEDDING_DIM, 1.0f);
 
    for (int l = 0; l < NUM_LAYERS; l++) {
        // the inputs are z_pos
        build_LUT(&m->FFN[l], N_C, EMBEDDING_DIM); 
        for (int h = 0; h < NUM_HEADS; h++) {
            m->head[l][h].Positional_encoding = malloc(sizeof(float)*CONTEXT_SIZE*N_T*POSITIONAL_DIM);
            random_vector(m->head[l][h].Positional_encoding[0][0], CONTEXT_SIZE*N_T*POSITIONAL_DIM, 1.0f);
            // the inputs are concatenated [Q, P, PE]
            build_LUT(&m->head[l][h].V, N_C + N_C + POSITIONAL_DIM, EMBEDDING_DIM); 
        }
    }
    build_LUT(&m->unembedder,  N_C, VOCAB_SIZE);
}

void free_Model(Model* m) {

    for (int l = 0; l < NUM_LAYERS; l++) {
        free_LUT(&m->FFN[l]);
        for (int h = 0; h < NUM_HEADS; h++) {
            free_LUT(&m->head[l][h].V);
        }
    }
    free_LUT(&m->unembedder);
}

void attention_forward(AttentionHead* head, float x[CONTEXT_SIZE][EMBEDDING_DIM], float y[CONTEXT_SIZE][EMBEDDING_DIM]) {

    for (int pos = 0; pos < CONTEXT_SIZE; pos++) { 
        cache_index(&head->V, &head->V_cache[pos], x[pos]);
        cache_PE_index(&head->PE_cache[pos], head->Positional_encoding[pos]);
    }
    
    for (int pos = 1; pos < CONTEXT_SIZE; pos++) {
        for (int pos1 = 0; pos1 < pos; pos1++) {
            concatenated_LUT_forward(&head->V, &head->V_cache[pos], &head->V_cache[pos1], &head->PE_cache[pos-pos1], y[pos]);
        }
    }
}

void attention_backward(AttentionHead* head, float x_grad[CONTEXT_SIZE][EMBEDDING_DIM], float y_grad[CONTEXT_SIZE][EMBEDDING_DIM]) {

    float pos_grad[CONTEXT_SIZE][N_T][POSITIONAL_DIM];
    memset(pos_grad, 0, CONTEXT_SIZE*N_T*POSITIONAL_DIM*sizeof(float));

    for (int pos = 1; pos < CONTEXT_SIZE; pos++) { 
        for (int pos1 = 0; pos1 < pos; pos1++) { 
            concatenated_LUT_backward(&head->V, &head->V_cache[pos], &head->V_cache[pos1], &head->PE_cache[pos-pos1],  x_grad[pos], x_grad[pos1], pos_grad[pos-pos1], y_grad[pos]); 
        }
    }

    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        for (int i = 0; i < N_T; i++) {
            for (int k = 0; k < POSITIONAL_DIM; k++) {
                head->Positional_encoding[pos][i][k] -= learning_rate * pos_grad[pos][i][k];
            }
        }
    }
}

void model_forward(Model* m) {

    for (int l = 0; l < NUM_LAYERS; l++) {

        // AttentionHead from all z to all z   
        float x[CONTEXT_SIZE][EMBEDDING_DIM];
        memcpy(x, m->z, CONTEXT_SIZE*EMBEDDING_DIM*sizeof(float)); // each head will be looking at the same input
        for (int h = 0; h < NUM_HEADS; h++) {
            attention_forward(&m->head[l][h], x, m->z); // resnet connections: add to the output from the previous layer, m->z
        }
    
        // FFN from z_pos to z_pos.
        // For attention-only mode, comment the 4 lines below and 3 lines in the next function
        for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
            cache_index(&m->FFN[l], &m->FFN_cache[l][pos], m->z[pos]);    // resnet connections: from m->z
            LUT_forward(&m->FFN[l], &m->FFN_cache[l][pos], m->z[pos]);    // back to m->z
        }
    }
    
    memset(m->output, 0, CONTEXT_SIZE*VOCAB_SIZE*sizeof(float));
    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        cache_index(&m->unembedder, &m->unembedder_vars[pos], m->z[pos]);    
        LUT_forward(&m->unembedder, &m->unembedder_vars[pos], m->output[pos]); 
    }
}

void model_backward(Model* m) {

    float y_grad[CONTEXT_SIZE][EMBEDDING_DIM]; 
    float x_grad[CONTEXT_SIZE][EMBEDDING_DIM];
    memset(x_grad, 0, CONTEXT_SIZE*EMBEDDING_DIM*sizeof(float));

    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        LUT_backward(&m->unembedder, &m->unembedder_vars[pos], x_grad[pos], m->output[pos]); 
    }

    for (int l = NUM_LAYERS-1; l >= 0; l--) {

        // FFN from z_pos to z_pos
        memcpy(y_grad, x_grad, CONTEXT_SIZE*EMBEDDING_DIM*sizeof(float)); // don't zero-out x_grad, but add to it (resnet connections)
        // For attention-only mode, comment the 3 lines below and 4 lines in the previous function
        for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
            LUT_backward(&m->FFN[l], &m->FFN_cache[l][pos], x_grad[pos], y_grad[pos]);
        }

        // AttentionHead from all z to all z
        memcpy(y_grad, x_grad, CONTEXT_SIZE*EMBEDDING_DIM*sizeof(float)); // don't zero-out x_grad, but add to it (resnet connections)
        for (int h = 0; h < NUM_HEADS; h++) {
            attention_backward(&m->head[l][h], x_grad, y_grad);
        }
    }

    // no need to compute gradients for the embedder; just update the synaptic values
    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        for (int k = 0; k < EMBEDDING_DIM; k++) {
            // does not improve performance in character prediction mode, so OK to disable
            //m->Token_embedder[ m->tokens[pos] ][k] -= learning_rate * x_grad[pos][k]; 
        }
    }
}

void model_training_step(Model* m) {

    model_forward(m);
    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        softmax(m->output[pos], VOCAB_SIZE, 1.0f);
        m->output[pos][ m->tokens[pos+1] ] -= 1.0f; // output become a gradient
    }
    model_backward(m);
}





// ===================== Harness: proper enwik8 split, Hogwild threads =====================
typedef struct { unsigned char* data; long length; } Text;
Text load_slice(const char* fname, long start, long len) {
    Text t; FILE* f = fopen(fname, "rb"); if (!f) { printf("cannot open %s\n", fname); exit(1); }
    fseek(f, start, SEEK_SET); t.data = malloc(len); t.length = fread(t.data, 1, len, f); fclose(f); return t;
}
static inline unsigned long xs(unsigned long* s) { *s ^= *s << 13; *s ^= *s >> 7; *s ^= *s << 17; return *s; }
void load_snippet(Model* m, unsigned char* p) {
    for (int pos = 0; pos < CONTEXT_SIZE; pos++) {
        memcpy(m->z[pos], m->Token_embedder[p[pos]], EMBEDDING_DIM*sizeof(float)); m->tokens[pos] = p[pos]; }
    m->tokens[CONTEXT_SIZE] = p[CONTEXT_SIZE];
}
double evaluate(Model* m, Text* T, long* idx, int n) { // same metric as original: last position, 32-char context
    double loss = 0;
    for (int i = 0; i < n; i++) {
        load_snippet(m, T->data + idx[i]); model_forward(m);
        softmax(m->output[CONTEXT_SIZE-1], VOCAB_SIZE, 1.0f);
        loss += -log(m->output[CONTEXT_SIZE-1][m->tokens[CONTEXT_SIZE]] + 1e-30);
    }
    return loss / n;
}
Model* master; Text train; long tr_n; unsigned char* reserved;
atomic_long global_t = 0; long max_steps; atomic_int stop_flag = 0;
void* worker(void* arg) {
    unsigned long seed = 88172645463325252UL + 7919*(long)arg;
    Model* m = malloc(sizeof(Model)); memcpy(m, master, sizeof(Model)); // shares LUTs + PE via pointers
    while (!stop_flag) {
        long t = atomic_fetch_add(&global_t, 1); if (t >= max_steps) break;
        long s; do { s = xs(&seed) % tr_n; } while (reserved && reserved[s]);
        load_snippet(m, train.data + s);
        learning_rate = LEARNING_RATE;
        model_training_step(m);
    }
    return NULL;
}
// usage: snn MODE enwik8 out.csv max_steps max_seconds eval_seconds n_val n_test threads
//  proper: train [0,90M) | val [90M,95M) | test [95M,100M)
//  leaky : original protocol on [0,95M): val positions drawn from the training text with +-32 exclusion
int main(int argc, char** argv) {
    const char* mode = argv[1]; const char* fname = argv[2]; const char* out = argv[3];
    max_steps = atol(argv[4]); long max_sec = atol(argv[5]); long eval_sec = atol(argv[6]);
    int NV = atoi(argv[7]), NT = atoi(argv[8]), TH = atoi(argv[9]);
    int proper = !strcmp(mode, "proper");
    srand(1);
    train = load_slice(fname, 0, proper ? 90000000L : 95000000L);
    Text valid = proper ? load_slice(fname, 90000000L, 5000000L) : train;
    Text test = load_slice(fname, 95000000L, 5000000L);
    tr_n = train.length - CONTEXT_SIZE - 1;
    unsigned long seed = 12345;
    long* vidx = malloc(NV*sizeof(long)); long* tidx = malloc(NT*sizeof(long));
    reserved = proper ? NULL : calloc(tr_n, 1);
    for (int i = 0; i < NV; i++) { vidx[i] = xs(&seed) % (valid.length - CONTEXT_SIZE - 1);
        if (!proper) for (int j = -CONTEXT_SIZE; j <= CONTEXT_SIZE; j++) { long q = vidx[i]+j; if (q>=0 && q<tr_n) reserved[q]=1; } }
    for (int i = 0; i < NT; i++) tidx[i] = xs(&seed) % (test.length - CONTEXT_SIZE - 1);
    FILE* f = fopen("eval_positions.txt", "w"); // so baselines are scored on identical positions
    fprintf(f, "%d %d\n", NV, NT); for (int i=0;i<NV;i++) fprintf(f,"%ld\n",vidx[i]); for (int i=0;i<NT;i++) fprintf(f,"%ld\n",tidx[i]); fclose(f);

    master = malloc(sizeof(Model)); build_Model(master);
    Model* ev = malloc(sizeof(Model));
    f = fopen(out, "w"); fprintf(f, "step,val_bpc,seconds\n"); fclose(f);
    pthread_t th[64]; for (long k = 0; k < TH; k++) pthread_create(&th[k], NULL, worker, (void*)k);
    time_t t0 = time(NULL); time_t last = 0;
    while (1) {
        long el = time(NULL) - t0; long t = global_t;
        if (el - last >= eval_sec || t >= max_steps || el >= max_sec) {
            last = el; memcpy(ev, master, sizeof(Model));
            double v = evaluate(ev, &valid, vidx, NV) / log(2);
            f = fopen(out, "a"); fprintf(f, "%ld,%f,%ld\n", t, v, el); fclose(f);
            printf("[%s] step=%ld val_bpc=%.4f elapsed=%lds\n", mode, t, v, el); fflush(stdout);
            if (t >= max_steps || el >= max_sec) break;
        }
        usleep(200000);
    }
    stop_flag = 1; for (int k = 0; k < TH; k++) pthread_join(th[k], NULL);
    memcpy(ev, master, sizeof(Model));
    double te = evaluate(ev, &test, tidx, NT) / log(2);
    printf("[%s] FINAL test bpc (bytes [95M,100M) of the data file, %d positions) = %.4f after %ld steps\n", mode, NT, te, (long)global_t);
    f = fopen(out, "a"); fprintf(f, "# final_test_bpc=%f steps=%ld\n", te, (long)global_t); fclose(f);
    return 0;
}
