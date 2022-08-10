log_level = 'INFO'
load_from = None
resume_from = None
dist_params = dict(backend='nccl')
workflow = [('train', 1)]
checkpoint_config = dict(interval=10)
evaluation = dict(interval=25, metric='mAP', key_indicator='AP', rle_score=True)

optimizer = dict(
    type='AdamW',
    lr=5e-4,
    betas=(0.9, 0.999),
    weight_decay=0.01,
    paramwise_cfg = dict(
        custom_keys={
            'sampling_offsets': dict(lr_mult=0.1),
            'reference_points': dict(lr_mult=0.1),
            'neck': dict(lr_mult=2.0, decay_mult=0.01),
            'keypoint_head': dict(lr_mult=2.0, decay_mult=0.01),
        },
    )
)
optimizer_config = dict(grad_clip=None)
lr_config = dict(
    policy='step',
    warmup='linear',
    warmup_iters=500,
    warmup_ratio=0.001,
    step=[255, 310])
total_epochs = 325

log_config = dict(
    interval=50, hooks=[
        dict(type='TextLoggerHook'),
        dict(type='TensorboardLoggerHook'),
    ])

channel_cfg = dict(
    num_output_channels=17,
    dataset_joints=17,
    dataset_channel=[
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
    ],
    inference_channel=[
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
    ])

emb_dim = 256

# model settings
norm_cfg = dict(type='SyncBN', requires_grad=True)
model = dict(
    type='Poseur',
    pretrained='hrt_tiny.pth', # Set the path to pretrained backbone here
    backbone=dict(
        type='HRT',
        in_channels=3,
        norm_cfg=norm_cfg,
        extra=dict(
            drop_path_rate=0.1,
            stage1=dict(
                num_modules=1,
                num_branches=1,
                block='BOTTLENECK',
                num_blocks=(2, ),
                num_channels=(64, ),
                num_heads=[2],
                num_mlp_ratios=[4]),
            stage2=dict(
                num_modules=1,
                num_branches=2,
                block='TRANSFORMER_BLOCK',
                num_blocks=(2, 2),
                num_channels=(18, 36),
                num_heads = [1, 2],
                num_mlp_ratios = [4, 4],
                num_window_sizes = [7, 7]),
            stage3=dict(
                num_modules=3,
                num_branches=3,
                block='TRANSFORMER_BLOCK',
                num_blocks=(2, 2, 2),
                num_channels=(18, 36, 72),
                num_heads = [1, 2, 4],
                num_mlp_ratios = [4, 4, 4],
                num_window_sizes = [7, 7, 7]),
            stage4=dict(
                num_modules=2,
                num_branches=4,
                block='TRANSFORMER_BLOCK',
                num_blocks=(2, 2, 2, 2),
                num_channels=(18, 36, 72, 144),
                num_heads = [1, 2, 4, 8],
                num_mlp_ratios = [4, 4, 4, 4],
                num_window_sizes = [7, 7, 7, 7],
                multiscale_output=True,
                )
            )),
    neck=dict(
        type='ChannelMapper',
        in_channels=[18, 36, 72, 144],
        kernel_size=1,
        out_channels=emb_dim,
        act_cfg=None,
        norm_cfg=dict(type='GN', num_groups=32),
    ),
    keypoint_head=dict(
        type='Poseur_noise_sample',
        in_channels=512,
        num_queries=17,
        num_reg_fcs=2,
        num_joints=channel_cfg['num_output_channels'],
        with_box_refine=True,
        loss_coord_enc=dict(type='RLELoss_poseur', use_target_weight=True),
        loss_coord_dec=dict(type='RLELoss_poseur', use_target_weight=True),
        # loss_coord_dec=dict(type='L1Loss', use_target_weight=True, loss_weight=5),
        loss_hp_keypoint=dict(type='JointsMSELoss', use_target_weight=True, loss_weight=10),
        # loss_coord_keypoint=dict(type='L1Loss', use_target_weight=True, loss_weight=1),
        positional_encoding=dict(
            type='SinePositionalEncoding',
            num_feats=emb_dim//2,
            normalize=True,
            offset=-0.5),
        transformer=dict(
            type='PoseurTransformer_v3',
            query_pose_emb = True,
            embed_dims = emb_dim,
            encoder=dict(
                type='DetrTransformerEncoder_zero_layer',
                num_layers=0,
                transformerlayers=dict(
                    type='BaseTransformerLayer',
                    ffn_cfgs = dict(
                        embed_dims=emb_dim,
                        ),
                    attn_cfgs=dict(
                        type='MultiScaleDeformableAttention',
                        num_levels=4,
                        num_points=4,
                        embed_dims=emb_dim),
                    
                    feedforward_channels=1024,
                    ffn_dropout=0.1,
                    operation_order=('self_attn', 'norm', 'ffn', 'norm'))),
            decoder=dict(
                type='DeformableDetrTransformerDecoder',
                num_layers=3,
                return_intermediate=True,
                transformerlayers=dict(
                    type='DetrTransformerDecoderLayer_grouped',
                    ffn_cfgs = dict(
                        embed_dims=emb_dim,
                        ),
                    attn_cfgs=[
                        dict(
                            type='MultiheadAttention',
                            embed_dims=emb_dim,
                            num_heads=8,
                            dropout=0.1),
                        dict(
                            type='MultiScaleDeformableAttention_post_value',
                            num_levels=4,
                            num_points=4,
                            embed_dims=emb_dim)
                    ],
                    feedforward_channels=1024,
                    ffn_dropout=0.1,
                    operation_order=('self_attn', 'norm', 'cross_attn', 'norm',
                                     'ffn', 'norm')))),
        as_two_stage=True,
        use_heatmap_loss=False,
    ),
    train_cfg=dict(image_size=[192, 256]),
    test_cfg = dict(
        image_size=[192, 256],
        flip_test=True,
        post_process='default',
        shift_heatmap=True,
        modulate_kernel=11)
)

data_cfg = dict(
    image_size=[192, 256],
    heatmap_size=[48, 64],
    num_output_channels=channel_cfg['num_output_channels'],
    num_joints=channel_cfg['dataset_joints'],
    dataset_channel=channel_cfg['dataset_channel'],
    inference_channel=channel_cfg['inference_channel'],
    soft_nms=False,
    # use_nms=False,
    nms_thr=1.0,
    oks_thr=0.9,
    vis_thr=0.2,
    det_bbox_thr=0.0,
    # use_gt_bbox=True,
    # bbox_file='',
    use_gt_bbox=False,
    bbox_file='data/coco/person_detection_results/'
    'COCO_val2017_detections_AP_H_56_person.json',

)

train_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='TopDownGetBboxCenterScale', padding=1.25),
    dict(type='TopDownRandomFlip', flip_prob=0.5),
    dict(
        type='TopDownHalfBodyTransform',
        num_joints_half_body=8,
        prob_half_body=0.3),
    dict(
        type='TopDownGetRandomScaleRotation', rot_factor=40, scale_factor=0.5),
    dict(type='TopDownAffine'),
    dict(type='ToTensor'),
    dict(
        type='NormalizeTensor',
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]),
    # dict(
    #     type='TopDownGenerateTarget',
    #     kernel=[(11, 11), (9, 9), (7, 7), (5, 5)],
    #     encoding='Megvii'),
    dict(
        target_type='wo_mask',
        type='TopDownGenerateCoordAndHeatMapTarget',
        encoding='MSRA',
        sigma=2),
    dict(
        type='Collect',
        keys=['img', 'coord_target', 'coord_target_weight', 'hp_target', 'hp_target_weight'],
        meta_keys=[
            'image_file', 'joints_3d', 'joints_3d_visible', 'center', 'scale',
            'rotation', 'bbox_score', 'flip_pairs'
        ]),
]

val_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='TopDownGetBboxCenterScale', padding=1.25),
    dict(type='TopDownAffine'),
    dict(type='ToTensor'),
    dict(
        type='NormalizeTensor',
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]),
    dict(
        type='Collect',
        keys=[
            'img',
        ],
        meta_keys=[
            'image_file', 'center', 'scale', 'rotation', 'bbox_score',
            'flip_pairs'
        ]),
]

test_pipeline = val_pipeline

data_root = 'data/coco'
data = dict(
    samples_per_gpu=32,
    # samples_per_gpu=64,
    workers_per_gpu=8,
    val_dataloader=dict(samples_per_gpu=32),
    test_dataloader=dict(samples_per_gpu=32),
    train=dict(
        type='TopDownCocoDataset',
        ann_file=f'{data_root}/annotations/person_keypoints_train2017.json',
        img_prefix=f'{data_root}/train2017/',
        # ann_file=f'{data_root}/annotations/person_keypoints_val2017.json',
        # img_prefix=f'{data_root}/val2017/',
        data_cfg=data_cfg,
        pipeline=train_pipeline),
    val=dict(
        type='TopDownCocoDataset',
        ann_file=f'{data_root}/annotations/person_keypoints_val2017.json',
        img_prefix=f'{data_root}/val2017/',
        data_cfg=data_cfg,
        pipeline=val_pipeline),
    test=dict(
        type='TopDownCocoDataset',
        ann_file=f'{data_root}/annotations/person_keypoints_val2017.json',
        img_prefix=f'{data_root}/val2017/',
        data_cfg=data_cfg,
        pipeline=val_pipeline),
)

fp16 = dict(loss_scale='dynamic')
