package com.yui.arsccturret.client;

import com.yui.arsccturret.CCTurretTile;
import software.bernie.geckolib.renderer.GeoBlockRenderer;

// in-world 描画。Ars 純正タレットの見た目(geo/texture/反動アニメ)で CCTurretTile を描く。
public class CCTurretRenderer extends GeoBlockRenderer<CCTurretTile> {
    public CCTurretRenderer() {
        super(new CCTurretModel());
    }
}
