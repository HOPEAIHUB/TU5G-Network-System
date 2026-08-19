/**
 * TU5G Payment Service — HOPE PAY & UPS PAY
 * Virtual Payment Address (VPA) system, wallet management, transactions
 */

const VPA_SUFFIX = '@upspay';

export async function handleRequest(req, res) {
  const body = await req.json();
  const base44 = createClientFromRequest(req);
  
  const { action } = body;
  
  try {
    if (action === 'create_vpa') {
      const { userId, preferredName } = body;
      
      // Check if user already has a VPA
      const existing = await base44.entities.VirtualWallet.list({ filter: { userId }, limit: 1 });
      if (existing && existing.length > 0 && existing[0].vpaAddress) {
        return Response.json({ success: true, vpa: existing[0].vpaAddress, walletId: existing[0].id });
      }
      
      // Generate VPA
      const vpaName = (preferredName || `user${userId.slice(-6)}`).toLowerCase().replace(/[^a-z0-9]/g, '');
      const vpaAddress = `${vpaName}${VPA_SUFFIX}`;
      
      // Create wallet with VPA
      let wallet;
      if (existing && existing.length > 0) {
        wallet = await base44.entities.VirtualWallet.update(existing[0].id, { vpaAddress });
      } else {
        wallet = await base44.entities.VirtualWallet.create({
          userId,
          balance: 0,
          currency: 'USD',
          vpaAddress,
        });
      }
      
      return Response.json({
        success: true,
        message: 'VPA created — UPS PAY ACTIVATED',
        vpa: vpaAddress,
        walletId: wallet.id,
      });
    }
    
    if (action === 'get_wallet') {
      const { userId } = body;
      const wallets = await base44.entities.VirtualWallet.list({ filter: { userId }, limit: 1 });
      
      if (!wallets || wallets.length === 0) {
        return Response.json({ success: false, message: 'Wallet not found' }, { status: 404 });
      }
      
      return Response.json({ success: true, wallet: wallets[0] });
    }
    
    if (action === 'add_funds') {
      const { userId, amount, source } = body;
      
      const wallets = await base44.entities.VirtualWallet.list({ filter: { userId }, limit: 1 });
      if (!wallets || wallets.length === 0) {
        return Response.json({ success: false, message: 'Wallet not found' }, { status: 404 });
      }
      
      const wallet = wallets[0];
      const newBalance = (wallet.balance || 0) + amount;
      
      await base44.entities.VirtualWallet.update(wallet.id, { balance: newBalance });
      
      // Record transaction
      await base44.entities.PaymentTransaction.create({
        userId,
        transactionType: 'add_funds',
        amount,
        currency: wallet.currency || 'USD',
        status: 'completed',
        description: `Funds added via ${source || 'card'}`,
        vpaTo: wallet.vpaAddress,
      });
      
      return Response.json({
        success: true,
        message: 'Funds added — HOPE PAY ACTIVATED',
        newBalance,
      });
    }
    
    if (action === 'create_payment') {
      const { userId, amount, description } = body;
      
      // Create pending payment transaction
      const tx = await base44.entities.PaymentTransaction.create({
        userId,
        transactionType: 'payment',
        amount,
        currency: 'USD',
        status: 'pending',
        description: description || 'E-SIM purchase',
      });
      
      return Response.json({
        success: true,
        paymentId: tx.id,
        amount,
        status: 'pending',
      });
    }
    
    if (action === 'complete_payment') {
      const { paymentId } = body;
      
      const txs = await base44.entities.PaymentTransaction.list({ filter: { id: paymentId }, limit: 1 });
      if (!txs || txs.length === 0) {
        return Response.json({ success: false, message: 'Payment not found' }, { status: 404 });
      }
      
      const tx = txs[0];
      
      // Deduct from wallet
      const wallets = await base44.entities.VirtualWallet.list({ filter: { userId: tx.userId }, limit: 1 });
      if (!wallets || wallets.length === 0) {
        return Response.json({ success: false, message: 'Wallet not found' }, { status: 404 });
      }
      
      const wallet = wallets[0];
      if ((wallet.balance || 0) < tx.amount) {
        await base44.entities.PaymentTransaction.update(tx.id, { status: 'failed' });
        return Response.json({ success: false, message: 'Insufficient balance' }, { status: 400 });
      }
      
      const newBalance = (wallet.balance || 0) - tx.amount;
      await base44.entities.VirtualWallet.update(wallet.id, { balance: newBalance });
      await base44.entities.PaymentTransaction.update(tx.id, { status: 'completed' });
      
      return Response.json({
        success: true,
        message: 'Payment completed',
        paymentId: tx.id,
        newBalance,
      });
    }
    
    if (action === 'transfer') {
      const { userId, toVpa, amount, description } = body;
      
      // Get sender wallet
      const senderWallets = await base44.entities.VirtualWallet.list({ filter: { userId }, limit: 1 });
      if (!senderWallets || senderWallets.length === 0) {
        return Response.json({ success: false, message: 'Sender wallet not found' }, { status: 404 });
      }
      
      const senderWallet = senderWallets[0];
      if ((senderWallet.balance || 0) < amount) {
        return Response.json({ success: false, message: 'Insufficient balance' }, { status: 400 });
      }
      
      // Get recipient wallet by VPA
      const recipientWallets = await base44.entities.VirtualWallet.list({ filter: { vpaAddress: toVpa }, limit: 1 });
      if (!recipientWallets || recipientWallets.length === 0) {
        return Response.json({ success: false, message: 'Recipient VPA not found' }, { status: 404 });
      }
      
      const recipientWallet = recipientWallets[0];
      
      // Transfer
      await base44.entities.VirtualWallet.update(senderWallet.id, { balance: (senderWallet.balance || 0) - amount });
      await base44.entities.VirtualWallet.update(recipientWallet.id, { balance: (recipientWallet.balance || 0) + amount });
      
      // Record transaction
      const tx = await base44.entities.PaymentTransaction.create({
        userId,
        transactionType: 'transfer',
        amount,
        currency: 'USD',
        status: 'completed',
        description: description || `Transfer to ${toVpa}`,
        vpaFrom: senderWallet.vpaAddress,
        vpaTo: toVpa,
      });
      
      return Response.json({
        success: true,
        message: 'Transfer completed — UPS PAY ACTIVATED',
        transactionId: tx.id,
        newBalance: (senderWallet.balance || 0) - amount,
      });
    }
    
    if (action === 'history') {
      const { userId, limit = 50 } = body;
      const transactions = await base44.entities.PaymentTransaction.list({
        filter: { userId },
        sort: { created_date: -1 },
        limit: parseInt(limit),
      });
      
      return Response.json({ success: true, transactions });
    }
    
    return Response.json({ success: false, message: 'Unknown action' }, { status: 400 });
  } catch (err) {
    console.error('Payment service error:', err);
    return Response.json({ success: false, message: 'Internal server error', error: err.message }, { status: 500 });
  }
}
