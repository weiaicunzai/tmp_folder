
# from collections import defaultdict

# import numpy as np

# import torch
# import torch.nn as nn
# import torch.nn.functional as F

# # sys.path.append('utils')
# # from proj_adaptive_softmax import ProjectedAdaptiveLogSoftmax
# # from log_uniform_sampler import LogUniformSampler, sample_logits


# class LogUniformSampler(object):
#     def __init__(self, range_max, n_sample):
#         """
#         Reference : https://github.com/tensorflow/tensorflow/blob/r1.10/tensorflow/python/ops/candidate_sampling_ops.py
#             `P(class) = (log(class + 2) - log(class + 1)) / log(range_max + 1)`

#         expected count can be approximated by 1 - (1 - p)^n
#         and we use a numerically stable version -expm1(num_tries * log1p(-p))

#         Our implementation fixes num_tries at 2 * n_sample, and the actual #samples will vary from run to run
#         """
#         with torch.no_grad():
#             self.range_max = range_max
#             log_indices = torch.arange(1., range_max+2., 1.).log_()
#             self.dist = (log_indices[1:] - log_indices[:-1]) / log_indices[-1]
#             # print('P', self.dist.numpy().tolist()[-30:])

#             self.log_q = (- (-self.dist.double().log1p_() * 2 * n_sample).expm1_()).log_().float()

#         self.n_sample = n_sample

#     def sample(self, labels):
#         """
#             labels: [b1, b2]
#         Return
#             true_log_probs: [b1, b2]
#             samp_log_probs: [n_sample]
#             neg_samples: [n_sample]
#         """

#         # neg_samples = torch.empty(0).long()
#         n_sample = self.n_sample
#         n_tries = 2 * n_sample

#         with torch.no_grad():
#             neg_samples = torch.multinomial(self.dist, n_tries, replacement=True).unique()
#             device = labels.device
#             neg_samples = neg_samples.to(device)
#             true_log_probs = self.log_q[labels].to(device)
#             samp_log_probs = self.log_q[neg_samples].to(device)
#             return true_log_probs, samp_log_probs, neg_samples

# def sample_logits(embedding, bias, labels, inputs, sampler):
#     """
#         embedding: an nn.Embedding layer
#         bias: [n_vocab]
#         labels: [b1, b2]
#         inputs: [b1, b2, n_emb]
#         sampler: you may use a LogUniformSampler
#     Return
#         logits: [b1, b2, 1 + n_sample]
#     """
#     true_log_probs, samp_log_probs, neg_samples = sampler.sample(labels)
#     n_sample = neg_samples.size(0)
#     b1, b2 = labels.size(0), labels.size(1)
#     all_ids = torch.cat([labels.view(-1), neg_samples])
#     all_w = embedding(all_ids)
#     true_w = all_w[: -n_sample].view(b1, b2, -1)
#     sample_w = all_w[- n_sample:].view(n_sample, -1)

#     all_b = bias[all_ids]
#     true_b = all_b[: -n_sample].view(b1, b2)
#     sample_b = all_b[- n_sample:]

#     hit = (labels[:, :, None] == neg_samples).detach()

#     true_logits = torch.einsum('ijk,ijk->ij',
#         [true_w, inputs]) + true_b - true_log_probs
#     sample_logits = torch.einsum('lk,ijk->ijl',
#         [sample_w, inputs]) + sample_b - samp_log_probs
#     sample_logits.masked_fill_(hit, -1e30)
#     logits = torch.cat([true_logits[:, :, None], sample_logits], -1)

#     return logits



# CUDA_MAJOR = int(torch.version.cuda.split('.')[0])
# CUDA_MINOR = int(torch.version.cuda.split('.')[1])

# class ProjectedAdaptiveLogSoftmax(nn.Module):
#     def __init__(self, n_token, d_embed, d_proj, cutoffs, div_val=1,
#                  keep_order=False):
#         super(ProjectedAdaptiveLogSoftmax, self).__init__()

#         self.n_token = n_token
#         self.d_embed = d_embed
#         self.d_proj = d_proj

#         self.cutoffs = cutoffs + [n_token]
#         self.cutoff_ends = [0] + self.cutoffs
#         self.div_val = div_val

#         self.shortlist_size = self.cutoffs[0]
#         self.n_clusters = len(self.cutoffs) - 1
#         self.head_size = self.shortlist_size + self.n_clusters

#         if self.n_clusters > 0:
#             self.cluster_weight = nn.Parameter(torch.zeros(self.n_clusters, self.d_embed))
#             self.cluster_bias = nn.Parameter(torch.zeros(self.n_clusters))

#         self.out_layers = nn.ModuleList()
#         self.out_projs = nn.ParameterList()

#         if div_val == 1:
#             for i in range(len(self.cutoffs)):
#                 if d_proj != d_embed:
#                     self.out_projs.append(
#                         nn.Parameter(torch.Tensor(d_proj, d_embed))
#                     )
#                 else:
#                     self.out_projs.append(None)

#             self.out_layers.append(nn.Linear(d_embed, n_token))
#         else:
#             for i in range(len(self.cutoffs)):
#                 l_idx, r_idx = self.cutoff_ends[i], self.cutoff_ends[i+1]
#                 d_emb_i = d_embed // (div_val ** i)

#                 self.out_projs.append(
#                     nn.Parameter(torch.Tensor(d_proj, d_emb_i))
#                 )

#                 self.out_layers.append(nn.Linear(d_emb_i, r_idx-l_idx))

#         self.keep_order = keep_order

#     def _compute_logit(self, hidden, weight, bias, proj):
#         if proj is None:
#             logit = F.linear(hidden, weight, bias=bias)
#         else:
#             # if CUDA_MAJOR <= 9 and CUDA_MINOR <= 1:
#             proj_hid = F.linear(hidden, proj.t().contiguous())
#             logit = F.linear(proj_hid, weight, bias=bias)
#             # else:
#             #     logit = torch.einsum('bd,de,ev->bv', (hidden, proj, weight.t()))
#             #     if bias is not None:
#             #         logit = logit + bias

#         return logit

#     def forward(self, hidden, target, keep_order=False):
#         '''
#             hidden :: [len*bsz x d_proj]
#             target :: [len*bsz]
#         '''

#         if hidden.size(0) != target.size(0):
#             raise RuntimeError('Input and target should have the same size '
#                                'in the batch dimension.')

#         if self.n_clusters == 0:
#             logit = self._compute_logit(hidden, self.out_layers[0].weight,
#                                         self.out_layers[0].bias, self.out_projs[0])
#             nll = -F.log_softmax(logit, dim=-1) \
#                     .gather(1, target.unsqueeze(1)).squeeze(1)
#         else:
#             # construct weights and biases
#             weights, biases = [], []
#             for i in range(len(self.cutoffs)):
#                 if self.div_val == 1:
#                     l_idx, r_idx = self.cutoff_ends[i], self.cutoff_ends[i + 1]
#                     weight_i = self.out_layers[0].weight[l_idx:r_idx]
#                     bias_i = self.out_layers[0].bias[l_idx:r_idx]
#                 else:
#                     weight_i = self.out_layers[i].weight
#                     bias_i = self.out_layers[i].bias

#                 if i == 0:
#                     weight_i = torch.cat(
#                         [weight_i, self.cluster_weight], dim=0)
#                     bias_i = torch.cat(
#                         [bias_i, self.cluster_bias], dim=0)

#                 weights.append(weight_i)
#                 biases.append(bias_i)

#             head_weight, head_bias, head_proj = weights[0], biases[0], self.out_projs[0]

#             head_logit = self._compute_logit(hidden, head_weight, head_bias, head_proj)
#             head_logprob = F.log_softmax(head_logit, dim=1)

#             nll = torch.zeros_like(target,
#                     dtype=hidden.dtype, device=hidden.device)

#             offset = 0
#             cutoff_values = [0] + self.cutoffs
#             for i in range(len(cutoff_values) - 1):
#                 l_idx, r_idx = cutoff_values[i], cutoff_values[i + 1]

#                 mask_i = (target >= l_idx) & (target < r_idx)
#                 indices_i = mask_i.nonzero().squeeze()

#                 if indices_i.numel() == 0:
#                     continue

#                 target_i = target.index_select(0, indices_i) - l_idx
#                 head_logprob_i = head_logprob.index_select(0, indices_i)

#                 if i == 0:
#                     logprob_i = head_logprob_i.gather(1, target_i[:,None]).squeeze(1)
#                 else:
#                     weight_i, bias_i, proj_i = weights[i], biases[i], self.out_projs[i]

#                     hidden_i = hidden.index_select(0, indices_i)

#                     tail_logit_i = self._compute_logit(hidden_i, weight_i, bias_i, proj_i)
#                     tail_logprob_i = F.log_softmax(tail_logit_i, dim=1)

#                     logprob_i = head_logprob_i[:, -i] \
#                               + tail_logprob_i.gather(1, target_i[:,None]).squeeze(1)

#                 if (hasattr(self, 'keep_order') and self.keep_order) or keep_order:
#                     nll.index_copy_(0, indices_i, -logprob_i)
#                 else:
#                     nll[offset:offset+logprob_i.size(0)].copy_(-logprob_i)

#                 offset += logprob_i.size(0)

#         return nll


# class PositionalEmbedding(nn.Module):
#     def __init__(self, demb):
#         super(PositionalEmbedding, self).__init__()

#         self.demb = demb

#         inv_freq = 1 / (10000 ** (torch.arange(0.0, demb, 2.0) / demb))
#         self.register_buffer('inv_freq', inv_freq)

#     def forward(self, pos_seq, bsz=None):
#         sinusoid_inp = torch.ger(pos_seq, self.inv_freq)
#         pos_emb = torch.cat([sinusoid_inp.sin(), sinusoid_inp.cos()], dim=-1)

#         if bsz is not None:
#             return pos_emb[:,None,:].expand(-1, bsz, -1)
#         else:
#             return pos_emb[:,None,:]


# class PositionwiseFF(nn.Module):
#     def __init__(self, d_model, d_inner, dropout, pre_lnorm=False):
#         super(PositionwiseFF, self).__init__()

#         self.d_model = d_model
#         self.d_inner = d_inner
#         self.dropout = dropout

#         self.CoreNet = nn.Sequential(
#             nn.Linear(d_model, d_inner), nn.ReLU(inplace=True),
#             nn.Dropout(dropout),
#             nn.Linear(d_inner, d_model),
#             nn.Dropout(dropout),
#         )

#         self.layer_norm = nn.LayerNorm(d_model)

#         self.pre_lnorm = pre_lnorm

#     def forward(self, inp):
#         if self.pre_lnorm:
#             ##### layer normalization + positionwise feed-forward
#             core_out = self.CoreNet(self.layer_norm(inp))

#             ##### residual connection
#             output = core_out + inp
#         else:
#             ##### positionwise feed-forward
#             core_out = self.CoreNet(inp)

#             ##### residual connection + layer normalization
#             output = self.layer_norm(inp + core_out)

#         return output

# class MultiHeadAttn(nn.Module):
#     def __init__(self, n_head, d_model, d_head, dropout, dropatt=0,
#                  pre_lnorm=False):
#         super(MultiHeadAttn, self).__init__()

#         self.n_head = n_head
#         self.d_model = d_model
#         self.d_head = d_head
#         self.dropout = dropout

#         self.q_net = nn.Linear(d_model, n_head * d_head, bias=False)
#         self.kv_net = nn.Linear(d_model, 2 * n_head * d_head, bias=False)

#         self.drop = nn.Dropout(dropout)
#         self.dropatt = nn.Dropout(dropatt)
#         self.o_net = nn.Linear(n_head * d_head, d_model, bias=False)

#         self.layer_norm = nn.LayerNorm(d_model)

#         self.scale = 1 / (d_head ** 0.5)

#         self.pre_lnorm = pre_lnorm

#     def forward(self, h, attn_mask=None, mems=None):
#         ##### multihead attention
#         # [hlen x bsz x n_head x d_head]

#         if mems is not None:
#             c = torch.cat([mems, h], 0)
#         else:
#             c = h

#         if self.pre_lnorm:
#             ##### layer normalization
#             c = self.layer_norm(c)

#         head_q = self.q_net(h)
#         head_k, head_v = torch.chunk(self.kv_net(c), 2, -1)

#         head_q = head_q.view(h.size(0), h.size(1), self.n_head, self.d_head)
#         head_k = head_k.view(c.size(0), c.size(1), self.n_head, self.d_head)
#         head_v = head_v.view(c.size(0), c.size(1), self.n_head, self.d_head)

#         # [qlen x klen x bsz x n_head]
#         attn_score = torch.einsum('ibnd,jbnd->ijbn', (head_q, head_k))
#         attn_score.mul_(self.scale)
#         if attn_mask is not None and attn_mask.any().item():
#             if attn_mask.dim() == 2:
#                 attn_score.masked_fill_(attn_mask[None,:,:,None], -float('inf'))
#             elif attn_mask.dim() == 3:
#                 attn_score.masked_fill_(attn_mask[:,:,:,None], -float('inf'))

#         # [qlen x klen x bsz x n_head]
#         attn_prob = F.softmax(attn_score, dim=1)
#         attn_prob = self.dropatt(attn_prob)

#         # [qlen x klen x bsz x n_head] + [klen x bsz x n_head x d_head] -> [qlen x bsz x n_head x d_head]
#         attn_vec = torch.einsum('ijbn,jbnd->ibnd', (attn_prob, head_v))
#         attn_vec = attn_vec.contiguous().view(
#             attn_vec.size(0), attn_vec.size(1), self.n_head * self.d_head)

#         ##### linear projection
#         attn_out = self.o_net(attn_vec)
#         attn_out = self.drop(attn_out)

#         if self.pre_lnorm:
#             ##### residual connection
#             output = h + attn_out
#         else:
#             ##### residual connection + layer normalization
#             output = self.layer_norm(h + attn_out)

#         return output

# class RelMultiHeadAttn(nn.Module):
#     def __init__(self, n_head, d_model, d_head, dropout, dropatt=0,
#                  tgt_len=None, ext_len=None, mem_len=None, pre_lnorm=False):
#         super(RelMultiHeadAttn, self).__init__()

#         self.n_head = n_head
#         self.d_model = d_model
#         self.d_head = d_head
#         self.dropout = dropout

#         self.qkv_net = nn.Linear(d_model, 3 * n_head * d_head, bias=False)

#         self.drop = nn.Dropout(dropout)
#         self.dropatt = nn.Dropout(dropatt)
#         self.o_net = nn.Linear(n_head * d_head, d_model, bias=False)

#         self.layer_norm = nn.LayerNorm(d_model)

#         self.scale = 1 / (d_head ** 0.5)

#         self.pre_lnorm = pre_lnorm

#     def _parallelogram_mask(self, h, w, left=False):
#         mask = torch.ones((h, w)).byte()
#         m = min(h, w)
#         mask[:m,:m] = torch.triu(mask[:m,:m])
#         mask[-m:,-m:] = torch.tril(mask[-m:,-m:])

#         if left:
#             return mask
#         else:
#             return mask.flip(0)

#     def _shift(self, x, qlen, klen, mask, left=False):
#         if qlen > 1:
#             zero_pad = torch.zeros((x.size(0), qlen-1, x.size(2), x.size(3)),
#                                     device=x.device, dtype=x.dtype)
#         else:
#             zero_pad = torch.zeros(0, device=x.device, dtype=x.dtype)

#         if left:
#             mask = mask.flip(1)
#             x_padded = torch.cat([zero_pad, x], dim=1).expand(qlen, -1, -1, -1)
#         else:
#             x_padded = torch.cat([x, zero_pad], dim=1).expand(qlen, -1, -1, -1)

#         x = x_padded.masked_select(mask[:,:,None,None]) \
#                     .view(qlen, klen, x.size(2), x.size(3))

#         return x

#     def _rel_shift(self, x, zero_triu=False):
#         zero_pad = torch.zeros((x.size(0), 1, *x.size()[2:]),
#                                device=x.device, dtype=x.dtype)
#         x_padded = torch.cat([zero_pad, x], dim=1)

#         x_padded = x_padded.view(x.size(1) + 1, x.size(0), *x.size()[2:])

#         x = x_padded[1:].view_as(x)

#         if zero_triu:
#             ones = torch.ones((x.size(0), x.size(1)))
#             x = x * torch.tril(ones, x.size(1) - x.size(0))[:,:,None,None]

#         return x

#     def forward(self, w, r, attn_mask=None, mems=None):
#         raise NotImplementedError

# class RelPartialLearnableMultiHeadAttn(RelMultiHeadAttn):
#     def __init__(self, *args, **kwargs):
#         super(RelPartialLearnableMultiHeadAttn, self).__init__(*args, **kwargs)

#         self.r_net = nn.Linear(self.d_model, self.n_head * self.d_head, bias=False)

#     def forward(self, w, r, r_w_bias, r_r_bias, attn_mask=None, mems=None):
#         qlen, rlen, bsz = w.size(0), r.size(0), w.size(1)  # 512, 512, 22

#         if mems is not None:
#             cat = torch.cat([mems, w], 0)
#             if self.pre_lnorm:
#                 w_heads = self.qkv_net(self.layer_norm(cat))
#             else:
#                 w_heads = self.qkv_net(cat) # cat: [512, 22, 512] ---> w_heads [512, 22, 1536]
#             r_head_k = self.r_net(r)

#             w_head_q, w_head_k, w_head_v = torch.chunk(w_heads, 3, dim=-1) # w_heads: [512, 22, 1536] --> [512, 22, 512], [512, 22, 512], [512, 22, 512]
#             w_head_q = w_head_q[-qlen:]
#         else:
#             if self.pre_lnorm:
#                 w_heads = self.qkv_net(self.layer_norm(w))
#             else:
#                 w_heads = self.qkv_net(w)
#             r_head_k = self.r_net(r)

#             w_head_q, w_head_k, w_head_v = torch.chunk(w_heads, 3, dim=-1)

#         klen = w_head_k.size(0)

#         w_head_q = w_head_q.view(qlen, bsz, self.n_head, self.d_head)           # qlen x bsz x n_head x d_head
#         w_head_k = w_head_k.view(klen, bsz, self.n_head, self.d_head)           # qlen x bsz x n_head x d_head
#         w_head_v = w_head_v.view(klen, bsz, self.n_head, self.d_head)           # qlen x bsz x n_head x d_head

#         r_head_k = r_head_k.view(rlen, self.n_head, self.d_head)                # qlen x n_head x d_head

#         #### compute attention score
#         rw_head_q = w_head_q + r_w_bias                                         # qlen x bsz x n_head x d_head
#         AC = torch.einsum('ibnd,jbnd->ijbn', (rw_head_q, w_head_k))             # qlen x klen x bsz x n_head

#         rr_head_q = w_head_q + r_r_bias
#         BD = torch.einsum('ibnd,jnd->ijbn', (rr_head_q, r_head_k))              # qlen x klen x bsz x n_head
#         BD = self._rel_shift(BD)

#         # [qlen x klen x bsz x n_head]
#         attn_score = AC + BD
#         attn_score.mul_(self.scale)

#         #### compute attention probability
#         if attn_mask is not None and attn_mask.any().item():
#             if attn_mask.dim() == 2:
#                 attn_score = attn_score.float().masked_fill(
#                     attn_mask[None,:,:,None], -float('inf')).type_as(attn_score)
#             elif attn_mask.dim() == 3:
#                 attn_score = attn_score.float().masked_fill(
#                     attn_mask[:,:,:,None], -float('inf')).type_as(attn_score)

#         # [qlen x klen x bsz x n_head]
#         attn_prob = F.softmax(attn_score, dim=1)
#         attn_prob = self.dropatt(attn_prob)

#         #### compute attention vector
#         attn_vec = torch.einsum('ijbn,jbnd->ibnd', (attn_prob, w_head_v))

#         # [qlen x bsz x n_head x d_head]
#         attn_vec = attn_vec.contiguous().view(
#             attn_vec.size(0), attn_vec.size(1), self.n_head * self.d_head)

#         ##### linear projection
#         attn_out = self.o_net(attn_vec)
#         attn_out = self.drop(attn_out)

#         if self.pre_lnorm:
#             ##### residual connection
#             output = w + attn_out
#         else:
#             ##### residual connection + layer normalization
#             output = self.layer_norm(w + attn_out)

#         return output

# class RelLearnableMultiHeadAttn(RelMultiHeadAttn):
#     def __init__(self, *args, **kwargs):
#         super(RelLearnableMultiHeadAttn, self).__init__(*args, **kwargs)

#     def forward(self, w, r_emb, r_w_bias, r_bias, attn_mask=None, mems=None):
#         # r_emb: [klen, n_head, d_head], used for term B
#         # r_w_bias: [n_head, d_head], used for term C
#         # r_bias: [klen, n_head], used for term D

#         qlen, bsz = w.size(0), w.size(1)

#         if mems is not None:
#             cat = torch.cat([mems, w], 0)
#             if self.pre_lnorm:
#                 w_heads = self.qkv_net(self.layer_norm(cat))
#             else:
#                 w_heads = self.qkv_net(cat)
#             w_head_q, w_head_k, w_head_v = torch.chunk(w_heads, 3, dim=-1)

#             w_head_q = w_head_q[-qlen:]
#         else:
#             if self.pre_lnorm:
#                 w_heads = self.qkv_net(self.layer_norm(w))
#             else:
#                 w_heads = self.qkv_net(w)
#             w_head_q, w_head_k, w_head_v = torch.chunk(w_heads, 3, dim=-1)

#         klen = w_head_k.size(0)

#         w_head_q = w_head_q.view(qlen, bsz, self.n_head, self.d_head)
#         w_head_k = w_head_k.view(klen, bsz, self.n_head, self.d_head)
#         w_head_v = w_head_v.view(klen, bsz, self.n_head, self.d_head)

#         if klen > r_emb.size(0):
#             r_emb_pad = r_emb[0:1].expand(klen-r_emb.size(0), -1, -1)
#             r_emb = torch.cat([r_emb_pad, r_emb], 0)
#             r_bias_pad = r_bias[0:1].expand(klen-r_bias.size(0), -1)
#             r_bias = torch.cat([r_bias_pad, r_bias], 0)
#         else:
#             r_emb = r_emb[-klen:]
#             r_bias = r_bias[-klen:]

#         #### compute attention score
#         rw_head_q = w_head_q + r_w_bias[None]                                   # qlen x bsz x n_head x d_head

#         AC = torch.einsum('ibnd,jbnd->ijbn', (rw_head_q, w_head_k))             # qlen x klen x bsz x n_head
#         B_ = torch.einsum('ibnd,jnd->ijbn', (w_head_q, r_emb))                  # qlen x klen x bsz x n_head
#         D_ = r_bias[None, :, None]                                              # 1    x klen x 1   x n_head
#         BD = self._rel_shift(B_ + D_)

#         # [qlen x klen x bsz x n_head]
#         attn_score = AC + BD
#         attn_score.mul_(self.scale)

#         #### compute attention probability
#         if attn_mask is not None and attn_mask.any().item():
#             if attn_mask.dim() == 2:
#                 attn_score.masked_fill_(attn_mask[None,:,:,None], -float('inf'))
#             elif attn_mask.dim() == 3:
#                 attn_score.masked_fill_(attn_mask[:,:,:,None], -float('inf'))

#         # [qlen x klen x bsz x n_head]
#         attn_prob = F.softmax(attn_score, dim=1)
#         attn_prob = self.dropatt(attn_prob)

#         #### compute attention vector
#         attn_vec = torch.einsum('ijbn,jbnd->ibnd', (attn_prob, w_head_v))

#         # [qlen x bsz x n_head x d_head]
#         attn_vec = attn_vec.contiguous().view(
#             attn_vec.size(0), attn_vec.size(1), self.n_head * self.d_head)

#         ##### linear projection
#         attn_out = self.o_net(attn_vec)
#         attn_out = self.drop(attn_out)

#         if self.pre_lnorm:
#             ##### residual connection
#             output = w + attn_out
#         else:
#             ##### residual connection + layer normalization
#             output = self.layer_norm(w + attn_out)

#         return output

# class DecoderLayer(nn.Module):
#     def __init__(self, n_head, d_model, d_head, d_inner, dropout, **kwargs):
#         super(DecoderLayer, self).__init__()

#         self.dec_attn = MultiHeadAttn(n_head, d_model, d_head, dropout, **kwargs)
#         self.pos_ff = PositionwiseFF(d_model, d_inner, dropout,
#                                      pre_lnorm=kwargs.get('pre_lnorm'))

#     def forward(self, dec_inp, dec_attn_mask=None, mems=None):

#         output = self.dec_attn(dec_inp, attn_mask=dec_attn_mask,
#                                mems=mems)
#         output = self.pos_ff(output)

#         return output

# class RelLearnableDecoderLayer(nn.Module):
#     def __init__(self, n_head, d_model, d_head, d_inner, dropout,
#                  **kwargs):
#         super(RelLearnableDecoderLayer, self).__init__()

#         self.dec_attn = RelLearnableMultiHeadAttn(n_head, d_model, d_head, dropout,
#                                          **kwargs)
#         self.pos_ff = PositionwiseFF(d_model, d_inner, dropout,
#                                      pre_lnorm=kwargs.get('pre_lnorm'))

#     def forward(self, dec_inp, r_emb, r_w_bias, r_bias, dec_attn_mask=None, mems=None):

#         output = self.dec_attn(dec_inp, r_emb, r_w_bias, r_bias,
#                                attn_mask=dec_attn_mask,
#                                mems=mems)
#         output = self.pos_ff(output)

#         return output

# class RelPartialLearnableDecoderLayer(nn.Module):
#     def __init__(self, n_head, d_model, d_head, d_inner, dropout,
#                  **kwargs):
#         super(RelPartialLearnableDecoderLayer, self).__init__()

#         self.dec_attn = RelPartialLearnableMultiHeadAttn(n_head, d_model,
#                             d_head, dropout, **kwargs)
#         self.pos_ff = PositionwiseFF(d_model, d_inner, dropout,
#                                      pre_lnorm=kwargs.get('pre_lnorm'))

#     def forward(self, dec_inp, r, r_w_bias, r_r_bias, dec_attn_mask=None, mems=None):

#         output = self.dec_attn(dec_inp, r, r_w_bias, r_r_bias,
#                                attn_mask=dec_attn_mask,
#                                mems=mems)
#         output = self.pos_ff(output)

#         return output


# class AdaptiveEmbedding(nn.Module):
#     def __init__(self, n_token, d_embed, d_proj, cutoffs, div_val=1,
#                  sample_softmax=False):
#         super(AdaptiveEmbedding, self).__init__()

#         self.n_token = n_token  # 204
#         self.d_embed = d_embed # 512

#         self.cutoffs = cutoffs + [n_token]
#         self.div_val = div_val
#         self.d_proj = d_proj # 512

#         self.emb_scale = d_proj ** 0.5

#         self.cutoff_ends = [0] + self.cutoffs  #[0, 204]

#         self.emb_layers = nn.ModuleList()
#         self.emb_projs = nn.ParameterList()
#         if div_val == 1:
#             self.emb_layers.append(
#                 nn.Embedding(n_token, d_embed, sparse=sample_softmax>0)
#             )
#             if d_proj != d_embed:
#                 self.emb_projs.append(nn.Parameter(torch.Tensor(d_proj, d_embed)))
#         else:
#             for i in range(len(self.cutoffs)):
#                 l_idx, r_idx = self.cutoff_ends[i], self.cutoff_ends[i+1]
#                 d_emb_i = d_embed // (div_val ** i)
#                 self.emb_layers.append(nn.Embedding(r_idx-l_idx, d_emb_i))
#                 self.emb_projs.append(nn.Parameter(torch.Tensor(d_proj, d_emb_i)))

#     def forward(self, inp):
#         if self.div_val == 1:
#             embed = self.emb_layers[0](inp)
#             if self.d_proj != self.d_embed:
#                 embed  = F.linear(embed, self.emb_projs[0])
#         else:
#             param = next(self.parameters())
#             inp_flat = inp.view(-1)
#             emb_flat = torch.zeros([inp_flat.size(0), self.d_proj],
#                 dtype=param.dtype, device=param.device)
#             for i in range(len(self.cutoffs)):
#                 l_idx, r_idx = self.cutoff_ends[i], self.cutoff_ends[i + 1]

#                 mask_i = (inp_flat >= l_idx) & (inp_flat < r_idx)
#                 indices_i = mask_i.nonzero().squeeze()

#                 if indices_i.numel() == 0:
#                     continue

#                 inp_i = inp_flat.index_select(0, indices_i) - l_idx
#                 emb_i = self.emb_layers[i](inp_i)
#                 emb_i = F.linear(emb_i, self.emb_projs[i])

#                 emb_flat.index_copy_(0, indices_i, emb_i)

#             embed = emb_flat.view(*inp.size(), self.d_proj)

#         embed.mul_(self.emb_scale)

#         return embed

# class MemTransformerLM(nn.Module):
#     def __init__(self, n_token, n_layer, n_head, d_model, d_head, d_inner,
#                  dropout, dropatt, tie_weight=True, d_embed=None,
#                  div_val=1, tie_projs=[False], pre_lnorm=False,
#                  tgt_len=None, ext_len=None, mem_len=None,
#                  cutoffs=[], adapt_inp=False,
#                  same_length=False, attn_type=0, clamp_len=-1,
#                  sample_softmax=-1):
#         super(MemTransformerLM, self).__init__()
#         self.n_token = n_token

#         d_embed = d_model if d_embed is None else d_embed
#         self.d_embed = d_embed
#         self.d_model = d_model
#         self.n_head = n_head
#         self.d_head = d_head

#         self.word_emb = AdaptiveEmbedding(n_token, d_embed, d_model, cutoffs,
#                                           div_val=div_val)

#         self.drop = nn.Dropout(dropout)

#         self.n_layer = n_layer

#         self.tgt_len = tgt_len # 512
#         self.mem_len = mem_len # 512
#         self.ext_len = ext_len # 0
#         self.max_klen = tgt_len + ext_len + mem_len

#         self.attn_type = attn_type # 0

#         self.layers = nn.ModuleList()
#         if attn_type == 0: # the default attention
#             for i in range(n_layer):
#                 self.layers.append(
#                     RelPartialLearnableDecoderLayer(
#                         n_head, d_model, d_head, d_inner, dropout,
#                         tgt_len=tgt_len, ext_len=ext_len, mem_len=mem_len,
#                         dropatt=dropatt, pre_lnorm=pre_lnorm)
#                 )
#         elif attn_type == 1: # learnable embeddings
#             for i in range(n_layer):
#                 self.layers.append(
#                     RelLearnableDecoderLayer(
#                         n_head, d_model, d_head, d_inner, dropout,
#                         tgt_len=tgt_len, ext_len=ext_len, mem_len=mem_len,
#                         dropatt=dropatt, pre_lnorm=pre_lnorm)
#                 )
#         elif attn_type in [2, 3]: # absolute embeddings
#             for i in range(n_layer):
#                 self.layers.append(
#                     DecoderLayer(
#                         n_head, d_model, d_head, d_inner, dropout,
#                         dropatt=dropatt, pre_lnorm=pre_lnorm)
#                 )

#         self.sample_softmax = sample_softmax
#         # use sampled softmax
#         if sample_softmax > 0:
#             self.out_layer = nn.Linear(d_model, n_token)
#             if tie_weight:
#                 self.out_layer.weight = self.word_emb.weight
#             self.tie_weight = tie_weight
#             self.sampler = LogUniformSampler(n_token, sample_softmax)

#         # use adaptive softmax (including standard softmax)
#         else:
#             self.crit = ProjectedAdaptiveLogSoftmax(n_token, d_embed, d_model,
#                                                     cutoffs, div_val=div_val)

#             if tie_weight:
#                 for i in range(len(self.crit.out_layers)):
#                     self.crit.out_layers[i].weight = self.word_emb.emb_layers[i].weight

#             if tie_projs:
#                 for i, tie_proj in enumerate(tie_projs):
#                     if tie_proj and div_val == 1 and d_model != d_embed:
#                         self.crit.out_projs[i] = self.word_emb.emb_projs[0]
#                     elif tie_proj and div_val != 1:
#                         self.crit.out_projs[i] = self.word_emb.emb_projs[i]

#         self.same_length = same_length
#         self.clamp_len = clamp_len

#         self._create_params()

#     def backward_compatible(self):
#         self.sample_softmax = -1

#     def _create_params(self):
#         if self.attn_type == 0: # default attention
#             self.pos_emb = PositionalEmbedding(self.d_model)
#             self.r_w_bias = nn.Parameter(torch.Tensor(self.n_head, self.d_head))
#             self.r_r_bias = nn.Parameter(torch.Tensor(self.n_head, self.d_head))
#         elif self.attn_type == 1: # learnable
#             self.r_emb = nn.Parameter(torch.Tensor(
#                     self.n_layer, self.max_klen, self.n_head, self.d_head))
#             self.r_w_bias = nn.Parameter(torch.Tensor(
#                     self.n_layer, self.n_head, self.d_head))
#             self.r_bias = nn.Parameter(torch.Tensor(
#                     self.n_layer, self.max_klen, self.n_head))
#         elif self.attn_type == 2: # absolute standard
#             self.pos_emb = PositionalEmbedding(self.d_model)
#         elif self.attn_type == 3: # absolute deeper SA
#             self.r_emb = nn.Parameter(torch.Tensor(
#                     self.n_layer, self.max_klen, self.n_head, self.d_head))

#     def reset_length(self, tgt_len, ext_len, mem_len):
#         self.tgt_len = tgt_len
#         self.mem_len = mem_len
#         self.ext_len = ext_len

#     def init_mems(self):
#         if self.mem_len > 0:
#             mems = []
#             param = next(self.parameters())
#             for i in range(self.n_layer+1):
#                 empty = torch.empty(0, dtype=param.dtype, device=param.device)
#                 mems.append(empty)

#             return mems
#         else:
#             return None

#     def _update_mems(self, hids, mems, qlen, mlen):
#         # does not deal with None
#         if mems is None: return None

#         # mems is not None
#         assert len(hids) == len(mems), 'len(hids) != len(mems)'

#         # There are `mlen + qlen` steps that can be cached into mems
#         # For the next step, the last `ext_len` of the `qlen` tokens
#         # will be used as the extended context. Hence, we only cache
#         # the tokens from `mlen + qlen - self.ext_len - self.mem_len`
#         # to `mlen + qlen - self.ext_len`.
#         with torch.no_grad():
#             new_mems = []
#             end_idx = mlen + max(0, qlen - 0 - self.ext_len)
#             beg_idx = max(0, end_idx - self.mem_len)
#             for i in range(len(hids)):

#                 cat = torch.cat([mems[i], hids[i]], dim=0) # cat[1024, 512, 512]
#                 new_mems.append(cat[beg_idx:end_idx].detach())

#         return new_mems

#     def _forward(self, dec_inp, mems=None):
#         qlen, bsz = dec_inp.size() # [512, 22]

#         word_emb = self.word_emb(dec_inp) # word_emb: [seq_len, bs, wdim]

#         mlen = mems[0].size(0) if mems is not None else 0
#         klen = mlen + qlen
#         if self.same_length:
#             all_ones = word_emb.new_ones(qlen, klen)
#             mask_len = klen - self.mem_len
#             if mask_len > 0:
#                 mask_shift_len = qlen - mask_len
#             else:
#                 mask_shift_len = qlen
#             dec_attn_mask = (torch.triu(all_ones, 1+mlen)
#                     + torch.tril(all_ones, -mask_shift_len)).byte()[:, :, None] # -1
#         else:
#             dec_attn_mask = torch.triu(    # [512, 512]
#                 word_emb.new_ones(qlen, klen), diagonal=1+mlen).byte()[:,:,None]

#         hids = []
#         if self.attn_type == 0: # default
#             pos_seq = torch.arange(klen-1, -1, -1.0, device=word_emb.device,
#                                    dtype=word_emb.dtype)
#             if self.clamp_len > 0:
#                 pos_seq.clamp_(max=self.clamp_len)
#             pos_emb = self.pos_emb(pos_seq)

#             core_out = self.drop(word_emb)
#             pos_emb = self.drop(pos_emb)

#             hids.append(core_out)
#             for i, layer in enumerate(self.layers):
#                 mems_i = None if mems is None else mems[i]
#                 core_out = layer(core_out, pos_emb, self.r_w_bias,
#                         self.r_r_bias, dec_attn_mask=dec_attn_mask, mems=mems_i)
#                 hids.append(core_out)  #core_out 512, 22, 512
#         elif self.attn_type == 1: # learnable
#             core_out = self.drop(word_emb)
#             hids.append(core_out)
#             for i, layer in enumerate(self.layers):
#                 if self.clamp_len > 0:
#                     r_emb = self.r_emb[i][-self.clamp_len :]
#                     r_bias = self.r_bias[i][-self.clamp_len :]
#                 else:
#                     r_emb, r_bias = self.r_emb[i], self.r_bias[i]

#                 mems_i = None if mems is None else mems[i]
#                 core_out = layer(core_out, r_emb, self.r_w_bias[i],
#                         r_bias, dec_attn_mask=dec_attn_mask, mems=mems_i)
#                 hids.append(core_out)
#         elif self.attn_type == 2: # absolute
#             pos_seq = torch.arange(klen - 1, -1, -1.0, device=word_emb.device,
#                                    dtype=word_emb.dtype)
#             if self.clamp_len > 0:
#                 pos_seq.clamp_(max=self.clamp_len)
#             pos_emb = self.pos_emb(pos_seq)

#             core_out = self.drop(word_emb + pos_emb[-qlen:])

#             hids.append(core_out)
#             for i, layer in enumerate(self.layers):
#                 mems_i = None if mems is None else mems[i]
#                 if mems_i is not None and i == 0:
#                     mems_i += pos_emb[:mlen]
#                 core_out = layer(core_out, dec_attn_mask=dec_attn_mask,
#                                  mems=mems_i)
#                 hids.append(core_out)
#         elif self.attn_type == 3:
#             core_out = self.drop(word_emb)

#             hids.append(core_out)
#             for i, layer in enumerate(self.layers):
#                 mems_i = None if mems is None else mems[i]
#                 if mems_i is not None and mlen > 0:
#                     cur_emb = self.r_emb[i][:-qlen]
#                     cur_size = cur_emb.size(0)
#                     if cur_size < mlen:
#                         cur_emb_pad = cur_emb[0:1].expand(mlen-cur_size, -1, -1)
#                         cur_emb = torch.cat([cur_emb_pad, cur_emb], 0)
#                     else:
#                         cur_emb = cur_emb[-mlen:]
#                     mems_i += cur_emb.view(mlen, 1, -1)
#                 core_out += self.r_emb[i][-qlen:].view(qlen, 1, -1)

#                 core_out = layer(core_out, dec_attn_mask=dec_attn_mask,
#                                  mems=mems_i)
#                 hids.append(core_out)

#         core_out = self.drop(core_out) # core_out [512, 22, 512]

#         new_mems = self._update_mems(hids, mems, mlen, qlen)

#         return core_out, new_mems

#     def forward(self, data, target, *mems):
#         # nn.DataParallel does not allow size(0) tensors to be broadcasted.
#         # So, have to initialize size(0) mems inside the model forward.
#         # Moreover, have to return new_mems to allow nn.DataParallel to piece
#         # them together.
#         if not mems: mems = self.init_mems()

#         tgt_len = target.size(0)
#         hidden, new_mems = self._forward(data, mems=mems)

#         pred_hid = hidden[-tgt_len:]
#         if self.sample_softmax > 0 and self.training:
#             assert self.tie_weight
#             logit = sample_logits(self.word_emb,
#                 self.out_layer.bias, target, pred_hid, self.sampler)
#             loss = -F.log_softmax(logit, -1)[:, :, 0]
#         else:
#             loss = self.crit(pred_hid.view(-1, pred_hid.size(-1)), target.view(-1))
#             loss = loss.view(tgt_len, -1)

#         if new_mems is None:
#             return [loss]
#         else:
#             return [loss] + new_mems

# if __name__ == '__main__':
#     import argparse

#     parser = argparse.ArgumentParser(description='unit test')

#     parser.add_argument('--n_layer', type=int, default=4, help='')
#     parser.add_argument('--n_rel_layer', type=int, default=4, help='')
#     parser.add_argument('--n_head', type=int, default=2, help='')
#     parser.add_argument('--d_head', type=int, default=2, help='')
#     parser.add_argument('--d_model', type=int, default=200, help='')
#     parser.add_argument('--d_embed', type=int, default=200, help='')
#     parser.add_argument('--d_inner', type=int, default=200, help='')
#     parser.add_argument('--dropout', type=float, default=0.0, help='')
#     parser.add_argument('--cuda', action='store_true', help='')
#     parser.add_argument('--seed', type=int, default=1111, help='')
#     parser.add_argument('--multi_gpu', action='store_true', help='')

#     args = parser.parse_args()

#     device = torch.device("cuda" if args.cuda else "cpu")

#     B = 4
#     tgt_len, mem_len, ext_len = 36, 36, 0
#     data_len = tgt_len * 20
#     args.n_token = 10000

#     # import data_utils

#     # data = torch.LongTensor(data_len*B).random_(0, args.n_token).to(device)
#     # diter = data_utils.LMOrderedIterator(data, B, tgt_len, device=device, ext_len=ext_len)

#     cutoffs = [args.n_token // 2]
#     tie_projs = [False] + [True] * len(cutoffs)

#     for div_val in [1, 2]:
#         for d_embed in [200, 100]:
#             model = MemTransformerLM(args.n_token, args.n_layer, args.n_head,
#                             args.d_model, args.d_head, args.d_inner, args.dropout,
#                             dropatt=args.dropout, tie_weight=True,
#                             d_embed=d_embed, div_val=div_val,
#                             tie_projs=tie_projs, pre_lnorm=True,
#                             tgt_len=tgt_len, ext_len=ext_len, mem_len=mem_len,
#                             cutoffs=cutoffs, attn_type=0).to(device)

#             print(sum(p.numel() for p in model.parameters()))

#             mems = tuple()
#             # for idx, (inp, tgt, seqlen) in enumerate(diter):
#                 # print('batch {}'.format(idx))

#             inp = torch.Tensor(512, 22)
#             tgt = torch.Tensor(512, 22)
#             out = model(inp, tgt, *mems)
#             mems = out[1:]

#             import sys; sys.exit()


# import cv2

# img = cv2.imread('/data/hdd1/by/tmp_folder/img.png')
# img = img[:512, :512, :]
# print(img.shape)
# cv2.imwrite('test_512_patch.jpg', img)
# def build_model(model_name, num_classes, dis_mem_len=512, alpha=-0.1, args=None):
def build_model(model_name, num_classes, args=None):
    # model_name =
    if model_name == 'mynet_A_s':
        from .my_net import MyNet
        # net = MyNet(n_classes=num_classes, n_dim=384, interval=100, dis_mem_len=64)
        # net = MyNet(n_dim=384, dis_mem_len=512)
        net = MyNet(n_dim=384, dis_mem_len=args.mem_len, alpha=args.alpha)
        # net = MyNet(n_classes=num_classes, n_dim=384, interval=4, dis_mem_len=2)
        return net

    if model_name == 'mynet_A_b':
        from .my_net import MyNet
        # net = MyNet(n_classes=num_classes, n_dim=384 * 2, interval=100, dis_mem_len=64)
        # net = MyNet(n_dim=384 * 2, dis_mem_len=512)
        net = MyNet(n_dim=384 * 2, dis_mem_len=args.mem_len)
        return net


    if model_name == 'vit_s':
        from .vit import vit_small
        net = vit_small(n_classes=num_classes)
        return net

    if model_name == 'vit_b':
        from .vit import vit_base
        net = vit_base(n_classes=num_classes)
        return net

    if model_name == 'transmil':
        from .transmil import TransMIL
        net = TransMIL(n_classes=num_classes)
        return net

    if model_name=='cm_trans':
        from .cmtrans import get_vit256, vit_small
        if args.weights:
            net = get_vit256(args.weights, num_classes=num_classes, max_mem_len=args.mem_len)
        else:
            net = vit_small(num_classes=num_classes, max_mem_len=args.mem_len)

        # net=(num_classes,dis_mem_len, alpha)
        return net
