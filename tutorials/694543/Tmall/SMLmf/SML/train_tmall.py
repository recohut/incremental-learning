from __future__ import division
from __future__ import print_function
import os
import numpy as np
from engine import *
from model import *
from utils import *

np.random.seed(1234)
tf.set_random_seed(123)

# load data to df
start_time = time.time()

data_df = pd.read_csv('../../../datasets/tmall_1mth_2014_item20user50k_1neg_30seq.csv')

print('Done loading data! time elapsed: {}'.format(time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))))

num_users = data_df['userId'].max() + 1
num_items = data_df['itemId'].max() + 1

train_config = {'method': 'SMLmf_by_date',
                'dir_name': 'SMLmf_train11-23_test24-30_5epoch_5epoch',  # edit train test period, transfer number of epochs, base number of epochs
                'pretrain_model': 'pretrain_train1-10_test11_10epoch_0.001',  # pretrained base model
                'train_start_date': 20141011,
                'train_end_date': 20141031,
                'test_start_date': 20141024,
                'cur_date': None,  # current incremental date
                'next_date': None,  # next incremental date
                'cur_set_size': None,  # current incremental dataset size
                'next_set_size': None,  # next incremental dataset size
                'date_alias': None,  # individual date directory alias to save ckpts
                'restored_ckpt_mode': 'best auc',  # mode to search the ckpt to restore: 'best auc', 'best logloss', 'last'
                'restored_ckpt': None,  # restored sml model checkpoint

                'n1': 10,
                'n2': 5,
                'l1': 20,

                'transfer_optimizer': 'adam',  # transfer module optimizer: adam, rmsprop, sgd
                'transfer_lr': None,  # transfer module learning rate
                'transfer_bs': 1024,  # transfer module batch size
                'transfer_num_epochs': 5,  # transfer module number of epochs
                'test_stop_train': False,  # whether to stop updating transfer module during test periods

                'base_optimizer': 'adam',  # base model optimizer: adam, rmsprop, sgd
                'base_lr': None,  # base model learning rate
                'base_bs': 1024,  # base model batch size
                'base_num_epochs': 5,  # base model number of epochs
                'shuffle': True,  # whether to shuffle the dataset for each epoch
                }

MF_hyperparams = {'num_users': num_users,
                  'num_items': num_items,
                  'user_embed_dim': 8,
                  'item_embed_dim': 8,
                  }


def collect_params():
    """
    collect previous period model parameters
    :return: prev_emb_dict, prev_bias_dict
    """

    collect_params_start_time = time.time()

    emb_ls = ['user_emb_w', 'item_emb_w']
    bias_ls = ['user_b', 'item_b']

    prev_emb_dict_ = {name: tf.train.load_checkpoint(train_config['restored_ckpt']).get_tensor(name)
                      for name, _ in tf.train.list_variables(train_config['restored_ckpt']) if name in emb_ls}
    prev_bias_dict_ = {name: tf.train.load_checkpoint(train_config['restored_ckpt']).get_tensor(name)
                       for name, _ in tf.train.list_variables(train_config['restored_ckpt']) if name in bias_ls}

    print('collect params time elapsed: {}'.format(
        time.strftime('%H:%M:%S', time.gmtime(time.time() - collect_params_start_time))))

    return prev_emb_dict_, prev_bias_dict_


def train_base():

    # create an engine instance with sml_model
    engine = Engine(sess, sml_model)

    train_start_time = time.time()

    max_auc = 0
    best_logloss = 0

    for epoch_id in range(1, train_config['base_num_epochs'] + 1):

        print('Training Base Model Epoch {} Start!'.format(epoch_id))

        base_loss_cur_avg = engine.base_train_an_epoch(epoch_id, cur_set, train_config)
        print('Epoch {} Done! time elapsed: {}, base_loss_cur_avg {:.4f}'.format(
            epoch_id,
            time.strftime('%H:%M:%S', time.gmtime(time.time() - train_start_time)),
            base_loss_cur_avg))

        cur_auc, cur_logloss = engine.test(cur_set, train_config)
        next_auc, next_logloss = engine.test(next_set, train_config)
        print('cur_auc {:.4f}, cur_logloss {:.4f}, next_auc {:.4f}, next_logloss {:.4f}'.format(
            cur_auc,
            cur_logloss,
            next_auc,
            next_logloss))
        print('time elapsed {}'.format(time.strftime('%H:%M:%S', time.gmtime(time.time() - train_start_time))))

        print('')

        # save checkpoint
        if i >= train_config['test_start_date'] and train_config['test_stop_train']:
            checkpoint_alias = 'Epoch{}_TestAUC{:.4f}_TestLOGLOSS{:.4f}.ckpt'.format(
                epoch_id,
                next_auc,
                next_logloss)
            checkpoint_path = os.path.join(ckpts_dir, checkpoint_alias)
            saver.save(sess, checkpoint_path)

        if next_auc > max_auc:
            max_auc = next_auc
            best_logloss = next_logloss

    if i >= train_config['test_start_date']:
        test_aucs.append(max_auc)
        test_loglosses.append(best_logloss)


def train_transfer():

    # create an engine instance with sml_model
    engine = Engine(sess, sml_model)

    train_start_time = time.time()

    for epoch_id in range(1, train_config['transfer_num_epochs'] + 1):

        print('Training Transfer Module Epoch {} Start!'.format(epoch_id))

        transfer_loss_next_avg = engine.transfer_train_an_epoch(epoch_id, next_set, train_config)
        print('Epoch {} Done! time elapsed: {}, transfer_loss_next_avg {:.4f}'.format(
            epoch_id,
            time.strftime('%H:%M:%S', time.gmtime(time.time() - train_start_time)),
            transfer_loss_next_avg))

        cur_auc, cur_logloss = engine.test(cur_set, train_config)
        next_auc, next_logloss = engine.test(next_set, train_config)
        print('cur_auc {:.4f}, cur_logloss {:.4f}, next_auc {:.4f}, next_logloss {:.4f}'.format(
            cur_auc,
            cur_logloss,
            next_auc,
            next_logloss))
        print('time elapsed {}'.format(time.strftime('%H:%M:%S', time.gmtime(time.time() - train_start_time))))

        print('')

        # update transferred params
        sml_model.update(sess)

        # save checkpoint
        checkpoint_alias = 'Epoch{}_TestAUC{:.4f}_TestLOGLOSS{:.4f}.ckpt'.format(
            epoch_id,
            next_auc,
            next_logloss)
        checkpoint_path = os.path.join(ckpts_dir, checkpoint_alias)
        saver.save(sess, checkpoint_path)


orig_dir_name = train_config['dir_name']

for transfer_lr in [1e-2]:

    for base_lr in [1e-2]:

        print('')
        print('transfer_lr', transfer_lr, 'base_lr', base_lr)

        train_config['transfer_lr'] = transfer_lr
        train_config['base_lr'] = base_lr

        train_config['dir_name'] = orig_dir_name + '_' + str(transfer_lr) + '_' + str(base_lr)
        print('dir_name: ', train_config['dir_name'])

        test_aucs = []
        test_loglosses = []

        for i in range(train_config['train_start_date'], train_config['train_end_date']):

            # configure cur_date, next_date
            train_config['cur_date'] = i
            train_config['next_date'] = i + 1
            print('')
            print('current date: {}, next date: {}'.format(
                train_config['cur_date'],
                train_config['next_date']))
            print('')

            # create current and next set
            cur_set = data_df[data_df['date'] == train_config['cur_date']]
            next_set = data_df[data_df['date'] == train_config['next_date']]
            train_config['cur_set_size'] = len(cur_set)
            train_config['next_set_size'] = len(next_set)
            print('current set size', len(cur_set), 'next set size', len(next_set))

            train_config['date_alias'] = 'date' + str(i)

            # checkpoints directory
            ckpts_dir = os.path.join('ckpts', train_config['dir_name'], train_config['date_alias'])
            if not os.path.exists(ckpts_dir):
                os.makedirs(ckpts_dir)

            if i == train_config['train_start_date']:
                search_alias = os.path.join('../pretrain/ckpts', train_config['pretrain_model'], 'Epoch*')
                train_config['restored_ckpt'] = search_ckpt(search_alias, mode=train_config['restored_ckpt_mode'])
            else:
                prev_date_alias = 'date' + str(i - 1)
                search_alias = os.path.join('ckpts', train_config['dir_name'], prev_date_alias, 'Epoch*')
                train_config['restored_ckpt'] = search_ckpt(search_alias, mode=train_config['restored_ckpt_mode'])
            print('restored checkpoint: {}'.format(train_config['restored_ckpt']))

            # write train_config to text file
            with open(os.path.join(ckpts_dir, 'config.txt'), mode='w') as f:
                f.write('train_config: ' + str(train_config) + '\n')
                f.write('\n')
                f.write('MF_hyperparams: ' + str(MF_hyperparams) + '\n')

            # collect previous period model parameters
            prev_emb_dict, prev_bias_dict = collect_params()

            # build sml model computation graph
            tf.reset_default_graph()
            sml_model = SMLmf(MF_hyperparams, prev_emb_dict, prev_bias_dict, train_config=train_config)

            # create session
            with tf.Session() as sess:

                # restore sml model (transfer module and base model)
                if i == train_config['train_start_date']:
                    sess.run([tf.global_variables_initializer(), tf.local_variables_initializer()])  # initialize transfer module
                    restorer = tf.train.Saver(var_list=[v for v in tf.global_variables() if 'transfer' not in v.name])  # restore base model
                    restorer.restore(sess, train_config['restored_ckpt'])
                else:
                    restorer = tf.train.Saver()  # restore transfer module and base model
                    restorer.restore(sess, train_config['restored_ckpt'])
                saver = tf.train.Saver()

                # test transfer module by training base model with it
                train_base()

                # train transfer module
                if i < train_config['test_start_date'] or not train_config['test_stop_train']:
                    train_transfer()

            if i >= train_config['test_start_date']:
                average_auc = sum(test_aucs) / len(test_aucs)
                average_logloss = sum(test_loglosses) / len(test_loglosses)
                print('test aucs', test_aucs)
                print('average auc', average_auc)
                print('')
                print('test loglosses', test_loglosses)
                print('average logloss', average_logloss)

                # write metrics to text file
                with open(os.path.join(ckpts_dir, 'test_metrics.txt'), mode='w') as f:
                    f.write('test_aucs: ' + str(test_aucs) + '\n')
                    f.write('average_auc: ' + str(average_auc) + '\n')
                    f.write('test_loglosses: ' + str(test_loglosses) + '\n')
                    f.write('average_logloss: ' + str(average_logloss) + '\n')
