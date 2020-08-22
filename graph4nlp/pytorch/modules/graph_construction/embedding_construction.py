import torch
from torch import nn
from torch.nn.utils.rnn import pad_packed_sequence, pack_padded_sequence
import dgl

from ..utils.generic_utils import to_cuda

class EmbeddingConstructionBase(nn.Module):
    """
    Base class for (initial) graph embedding construction.

    ...

    Attributes
    ----------
    feat : dict
        Raw features of graph nodes and/or edges.

    Methods
    -------
    forward(raw_text_data)
        Generate dynamic graph topology and embeddings.
    """

    def __init__(self):
        super(EmbeddingConstructionBase, self).__init__()

    def forward(self):
        raise NotImplementedError()

class EmbeddingConstructionBase(nn.Module):
    """Basic class for embedding construction.
    """
    def __init__(self):
        super(EmbeddingConstructionBase, self).__init__()

    def forward(self):
        """Compute initial node/edge embeddings.

        Raises
        ------
        NotImplementedError
            NotImplementedError.
        """
        raise NotImplementedError()

class EmbeddingConstruction(EmbeddingConstructionBase):
    """Initial graph embedding construction class.

    Parameters
    ----------
    word_vocab : Vocab
        The word vocabulary.
    word_emb_type : str or list of str
        Specify pretrained word embedding types including "w2v" and/or "bert".
    node_edge_emb_strategy : str
        Specify node/edge embedding strategies including "mean", "lstm",
        "gru", "bilstm" and "bigru".
    seq_info_encode_strategy : str
        Specify strategies of encoding sequential information in raw text
        data including "none", "lstm", "gru", "bilstm" and "bigru". You might
        want to do this in some situations, e.g., when all the nodes are single
        tokens extracted from the raw text.
    hidden_size : int, optional
        The hidden size of RNN layer, default: ``None``.
    fix_word_emb : boolean, optional
        Specify whether to fix pretrained word embeddings, default: ``True``.
    word_dropout : float, optional
        Dropout ratio for word embedding, default: ``None``.
    dropout : float, optional
        Dropout ratio for RNN embedding, default: ``None``.
    device : torch.device, optional
        Specify computation device (e.g., CPU), default: ``None`` for using CPU.
    """
    def __init__(self, word_vocab, word_emb_type,
                        node_edge_emb_strategy,
                        seq_info_encode_strategy,
                        hidden_size=None,
                        fix_word_emb=True,
                        word_dropout=None,
                        dropout=None,
                        device=None):
        super(EmbeddingConstruction, self).__init__()
        self.device = device
        self.word_dropout = word_dropout
        self.node_edge_emb_strategy = node_edge_emb_strategy
        self.seq_info_encode_strategy = seq_info_encode_strategy

        if isinstance(word_emb_type, str):
            word_emb_type = [word_emb_type]

        self.word_emb_layers = nn.ModuleList()
        if 'w2v' in word_emb_type:
            self.word_emb_layers.append(WordEmbedding(
                            word_vocab.embeddings.shape[0],
                            word_vocab.embeddings.shape[1],
                            pretrained_word_emb=word_vocab.embeddings,
                            fix_word_emb=fix_word_emb, device=self.device))

        if 'bert' in word_emb_type:
            self.word_emb_layers.append(BertEmbedding(fix_word_emb))

        if node_edge_emb_strategy == 'mean':
            self.node_edge_emb_layer = MeanEmbedding()
        elif node_edge_emb_strategy == 'lstm':
            self.node_edge_emb_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1],
                                    hidden_size, dropout=dropout,
                                    bidirectional=False,
                                    rnn_type='lstm', device=device)
        elif node_edge_emb_strategy == 'bilstm':
            self.node_edge_emb_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1],
                                    hidden_size, dropout=dropout,
                                    bidirectional=True,
                                    rnn_type='lstm', device=device)
        elif node_edge_emb_strategy == 'gru':
            self.node_edge_emb_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1],
                                    hidden_size, dropout=dropout,
                                    bidirectional=False,
                                    rnn_type='gru', device=device)
        elif node_edge_emb_strategy == 'bigru':
            self.node_edge_emb_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1],
                                    hidden_size, dropout=dropout,
                                    bidirectional=True,
                                    rnn_type='gru', device=device)
        else:
            raise RuntimeError('Unknown node_edge_emb_strategy: {}'.format(node_edge_emb_strategy))

        if seq_info_encode_strategy == 'none':
            self.seq_info_encode_layer = None
        elif seq_info_encode_strategy == 'lstm':
            self.seq_info_encode_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1] \
                                    if node_edge_emb_strategy == 'mean' else hidden_size,
                                    hidden_size, dropout=dropout,
                                    bidirectional=False,
                                    rnn_type='lstm', device=device)
        elif seq_info_encode_strategy == 'bilstm':
            self.seq_info_encode_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1] \
                                    if node_edge_emb_strategy == 'mean' else hidden_size,
                                    hidden_size, dropout=dropout,
                                    bidirectional=True,
                                    rnn_type='lstm', device=device)
        elif seq_info_encode_strategy == 'gru':
            self.seq_info_encode_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1] \
                                    if node_edge_emb_strategy == 'mean' else hidden_size,
                                    hidden_size, dropout=dropout,
                                    bidirectional=False,
                                    rnn_type='gru', device=device)
        elif seq_info_encode_strategy == 'bigru':
            self.seq_info_encode_layer = RNNEmbedding(
                                    word_vocab.embeddings.shape[1] \
                                    if node_edge_emb_strategy == 'mean' else hidden_size,
                                    hidden_size, dropout=dropout,
                                    bidirectional=True,
                                    rnn_type='gru', device=device)
        else:
            raise RuntimeError('Unknown seq_info_encode_strategy: {}'.format(seq_info_encode_strategy))

    def forward(self, input_tensor, item_size, num_items):
        """Compute initial node/edge embeddings.

        Parameters
        ----------
        input_tensor : torch.LongTensor
            The input word sequence tensor with shape :math:`(N, L)` where
            :math:`N` is the total number of items in the batched graph,
            and :math:`L` is the word sequence length.
        item_size : torch.LongTensor
            The length of word sequence per item with shape :math:`(N)`.
        num_items : torch.LongTensor
            The number of items per graph with shape :math:`(B,)`
            where :math:`B` is the number of graphs in the batched graph.

        Returns
        -------
        torch.Tensor
            The output item embeddings.
        """
        feat = []
        for word_emb_layer in self.word_emb_layers:
            feat.append(word_emb_layer(input_tensor))

        feat = torch.cat(feat, dim=-1)
        # if word_dropout is not None:
        #     dropout

        feat = self.node_edge_emb_layer(feat, item_size)
        if self.node_edge_emb_strategy in ('lstm', 'bilstm', 'gru', 'bigru'):
            feat = feat[-1]

        if self.seq_info_encode_layer is None:
            return feat
        else:
            # unbatching
            max_num_items = torch.max(num_items).item()
            new_feat = []
            start_idx = 0
            for i in range(num_items.shape[0]):
                tmp_feat = feat[int(start_idx): int(start_idx + num_items[i].item())]
                start_idx += num_items[i].item()
                if num_items[i].item() < max_num_items:
                    tmp_feat = torch.cat([tmp_feat, to_cuda(torch.zeros(
                        int(max_num_items - num_items[i].item()), tmp_feat.shape[1]), self.device)], 0)
                new_feat.append(tmp_feat)

            # computation
            new_feat = torch.stack(new_feat, 0)
            new_feat = self.seq_info_encode_layer(new_feat, num_items)
            if self.seq_info_encode_strategy in ('lstm', 'bilstm', 'gru', 'bigru'):
                new_feat = new_feat[0]

            # batching
            ret_feat = []
            for i in range(num_items.shape[0]):
                ret_feat.append(new_feat[i][:num_items[i].item()])

            ret_feat = torch.cat(ret_feat, 0)

            return ret_feat


    def forward2(self, graph, feat_name, item_size,
                    num_items, out_feat_name='node_feat'):
        """Compute initial node/edge embeddings.

        Parameters
        ----------
        graph : GraphData
            The input graph data.
        feat_name : str
            The field name for extracting the word sequence tensor.
        item_size : torch.LongTensor
            The length of word sequence per item with shape :math:`(N)`
            where :math:`N` is the number of total items in the batched graph.
        num_items : torch.LongTensor
            The number of items per graph with shape :math:`(B,)`
            where :math:`B` is the number of graphs in the batched graph.

        Returns
        -------
        GraphData
            The output graph data containing initial item embeddings.
        """
        input_tensor = graph.ndata[feat_name]
        feat = []
        for word_emb_layer in self.word_emb_layers:
            feat.append(word_emb_layer(input_tensor))

        feat = torch.cat(feat, dim=-1)
        feat = self.node_edge_emb_layer(feat, item_size)
        if self.node_edge_emb_strategy in ('lstm', 'bilstm', 'gru', 'bigru'):
            feat = feat[-1]

        graph.ndata[out_feat_name] = feat
        if self.seq_info_encode_layer is not None:
            graph_list = dgl.unbatch(graph)

            max_num_items = torch.max(num_items).item()
            new_feat = []
            for i, each in enumerate(graph_list):
                tmp_feat = each.ndata[out_feat_name]
                if tmp_feat.shape[0] < max_num_items:
                    tmp_feat = torch.cat([tmp_feat, to_cuda(torch.zeros(
                        max_num_items - tmp_feat.shape[0], tmp_feat.shape[1]), self.device)], 0)
                new_feat.append(tmp_feat)

            new_feat = torch.stack(new_feat, 0)
            new_feat = self.seq_info_encode_layer(new_feat, num_items)
            if self.seq_info_encode_strategy in ('lstm', 'bilstm', 'gru', 'bigru'):
                new_feat = new_feat[0]

            ret_feat = []
            for i in range(new_feat.shape[0]):
                ret_feat.append(new_feat[i][:num_items[i].item()])

            ret_feat = torch.cat(ret_feat, 0)

            graph.ndata[out_feat_name] = ret_feat

        return graph

class WordEmbedding(nn.Module):
    """Word embedding class.

    Parameters
    ----------
    vocab_size : int
        The word vocabulary size.
    emb_size : int
        The word embedding size.
    padding_idx : int, optional
        The padding index, default: ``0``.
    pretrained_word_emb : numpy.ndarray, optional
        The pretrained word embeddings, default: ``None``.
    fix_word_emb : boolean, optional
        Specify whether to fix pretrained word embeddings, default: ``True``.

    Examples
    ----------
    >>> word_emb_layer = WordEmbedding(1000, 300, padding_idx=0, pretrained_word_emb=None, fix_word_emb=True)
    """
    def __init__(self, vocab_size, emb_size, padding_idx=0,
                    pretrained_word_emb=None, fix_word_emb=True, device=None):
        super(WordEmbedding, self).__init__()
        self.word_emb_layer = nn.Embedding(vocab_size, emb_size, padding_idx=padding_idx,
                            _weight=torch.from_numpy(pretrained_word_emb).float()
                            if pretrained_word_emb is not None else None)
        self.device = device
        if self.device:
            self.word_emb_layer = self.word_emb_layer.to(self.device)

        if fix_word_emb:
            print('[ Fix word embeddings ]')
            for param in self.word_emb_layer.parameters():
                param.requires_grad = False

    def forward(self, input_tensor):
        """Compute word embeddings.

        Parameters
        ----------
        input_tensor : torch.LongTensor
            The input word index sequence, shape: [num_items, max_size].

        Returns
        -------
        torch.Tensor
            Word embedding matrix.
        """
        return self.word_emb_layer(input_tensor)

class BertEmbedding(nn.Module):
    """Bert embedding class.
    """
    def __init__(self, fix_word_emb):
        super(BertEmbedding, self).__init__()
        self.fix_word_emb = fix_word_emb

    def forward(self):
        raise NotImplementedError()

class MeanEmbedding(nn.Module):
    """Mean embedding class.
    """
    def __init__(self):
        super(MeanEmbedding, self).__init__()

    def forward(self, emb, len_):
        """Compute average embeddings.

        Parameters
        ----------
        emb : torch.Tensor
            The input embedding tensor.
        len_ : torch.Tensor
            The sequence length tensor.

        Returns
        -------
        torch.Tensor
            The average embedding tensor.
        """
        sumed_emb = torch.sum(emb, dim=1)
        len_ = len_.unsqueeze(1).expand_as(sumed_emb).float()
        return sumed_emb / len_


class RNNEmbedding(nn.Module):
    """RNN embedding class: apply the RNN network to a sequence of word embeddings.

    Parameters
    ----------
    input_size : int
        The input feature size.
    hidden_size : int
        The hidden layer size.
    dropout : float, optional
        Dropout ratio, default: ``None``.
    bidirectional : boolean, optional
        Whether to use bidirectional RNN, default: ``False``.
    rnn_type : str
        The RNN cell type, default: ``lstm``.
    device : torch.device, optional
        Specify computation device (e.g., CPU), default: ``None`` for using CPU.
    """
    def __init__(self, input_size, hidden_size,
                    dropout=None, bidirectional=False,
                    rnn_type='lstm', device=None):
        super(RNNEmbedding, self).__init__()
        if not rnn_type in ('lstm', 'gru'):
            raise RuntimeError('rnn_type is expected to be lstm or gru, got {}'.format(rnn_type))

        # if bidirectional:
        #     print('[ Using bidirectional {} encoder ]'.format(rnn_type))
        # else:
        #     print('[ Using {} encoder ]'.format(rnn_type))

        if bidirectional and hidden_size % 2 != 0:
            raise RuntimeError('hidden_size is expected to be even in the bidirectional mode!')

        self.dropout = dropout
        self.rnn_type = rnn_type
        self.device = device
        self.hidden_size = hidden_size // 2 if bidirectional else hidden_size
        self.num_directions = 2 if bidirectional else 1
        model = nn.LSTM if rnn_type == 'lstm' else nn.GRU
        self.model = model(input_size, self.hidden_size, 1, batch_first=True, bidirectional=bidirectional)
        if self.device:
            self.model = self.model.to(self.device)

    def forward(self, x, x_len):
        """Apply the RNN network to a sequence of word embeddings.

        Parameters
        ----------
        x : torch.Tensor
            The word embedding sequence.
        x_len : torch.LongTensor
            The input sequence length.

        Returns
        -------
        torch.Tensor
            The hidden states at every time step.
        torch.Tensor
            The hidden state at the last time step.
        """
        sorted_x_len, indx = torch.sort(x_len, 0, descending=True)
        x = pack_padded_sequence(x[indx], sorted_x_len.data.tolist(), batch_first=True)

        h0 = to_cuda(torch.zeros(self.num_directions, x_len.size(0), self.hidden_size), self.device)
        if self.rnn_type == 'lstm':
            c0 = to_cuda(torch.zeros(self.num_directions, x_len.size(0), self.hidden_size), self.device)
            packed_h, (packed_h_t, _) = self.model(x, (h0, c0))
            if self.num_directions == 2:
                packed_h_t = torch.cat([packed_h_t[i] for i in range(packed_h_t.size(0))], -1)
            else:
                packed_h_t = packed_h_t.squeeze(0)

        else:
            packed_h, packed_h_t = self.model(x, h0)
            if self.num_directions == 2:
                packed_h_t = packed_h_t.transpose(0, 1).contiguous().view(query_lengths.size(0), -1)
            else:
                packed_h_t = packed_h_t.squeeze(0)

        hh, _ = pad_packed_sequence(packed_h, batch_first=True)

        # restore the sorting
        _, inverse_indx = torch.sort(indx, 0)
        restore_hh = hh[inverse_indx]
        restore_packed_h_t = packed_h_t[inverse_indx]

        return restore_hh, restore_packed_h_t
